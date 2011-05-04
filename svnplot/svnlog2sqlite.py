'''
svnlog2sqlite.py
Copyright (C) 2009 Nitin Bhide (nitinbhide@gmail.com)

This module is part of SVNPlot (http://code.google.com/p/svnplot) and is released under
the New BSD License: http://www.opensource.org/licenses/bsd-license.php
--------------------------------------------------------------------------------------

python script to convert the Subversion log into an sqlite database
The idea is to use the generated SQLite database as input to Matplot lib for
creating various graphs and analysis. The graphs are inspired from graphs
generated by StatSVN/StatCVS.
'''

import svnlogiter
import datetime,calendar
import sqlite3
import sys,os
import logging
import traceback
from optparse import OptionParser

import svnlogiter

BINARYFILEXT = [ 'doc', 'xls', 'ppt', 'docx', 'xlsx', 'pptx', 'dot', 'dotx', 'ods', 'odm', 'odt', 'ott', 'pdf',
                 'o', 'a', 'obj', 'lib', 'dll', 'so', 'exe',
                 'jar', 'zip', 'z', 'gz', 'tar', 'rar','7z',
                 'pdb', 'idb', 'ilk', 'bsc', 'ncb', 'sbr', 'pch', 'ilk',
                 'bmp', 'dib', 'jpg', 'jpeg', 'png', 'gif', 'ico', 'pcd', 'wmf', 'emf', 'xcf', 'tiff', 'xpm',
                 'gho', 'mp3', 'wma', 'wmv','wav','avi'
                 ]
    
class SVNLog2Sqlite:
    def __init__(self, svnrepopath, sqlitedbpath,verbose=False,**kwargs):
        username=kwargs.pop('username', None)
        password=kwargs.pop('password',None)
        logging.info("Repo url : " + svnrepopath)
        self.svnclient = svnlogiter.SVNLogClient(svnrepopath,BINARYFILEXT,username=username, password=password)
        self.dbpath =sqlitedbpath
        self.dbcon =None
        self.verbose = verbose
        
    def convert(self, svnrevstartdate, svnrevenddate, bUpdLineCount=True, maxtrycount=3):
        #First check if this a full conversion or a partial conversion
        self.initdb()
        self.CreateTables()
        for trycount in range(0, maxtrycount):
            try:
                laststoredrev = self.getLastStoredRev()
                rootUrl = self.svnclient.getRootUrl()
                self.printVerbose("Root url found : %s" % rootUrl)
                (startrevno, endrevno) = self.svnclient.findStartEndRev(svnrevstartdate, svnrevenddate)
                self.printVerbose("Start-End Rev no : %d-%d" % (startrevno, endrevno))
                startrevno = max(startrevno,laststoredrev+1) 
                self.ConvertRevs(startrevno, endrevno, bUpdLineCount)
                #every thing is ok. Commit the changes.
                self.dbcon.commit()
            except Exception, expinst:
                logging.exception("Found Error")
                self.svnexception_handler(expinst)
                print "Trying again (%d)" % (trycount+1)            
        
        self.closedb()
        
    def initdb(self):
        self.dbcon = sqlite3.connect(self.dbpath, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        #self.dbcon.row_factory = sqlite3.Row

    def closedb(self):
        self.dbcon.commit()
        self.dbcon.close()

    def svnexception_handler(self, expinst):
        '''
        decide to continue or exit on the svn exception.
        '''
        self.dbcon.rollback()
        print "Found Error. Rolled back recent changes"
        print "Error type %s" % type(expinst)
        if( isinstance(expinst, AssertionError)):            
            exit(1)            
        exitAdvised = self.svnclient.printSvnErrorHint(expinst)
        if( exitAdvised):
            exit(1)
        
    def getLastStoredRev(self):
        cur = self.dbcon.cursor()
        cur.execute("select max(revno) from svnlog")
        lastStoreRev = 0
        
        row = cur.fetchone()
        if( row != None and len(row) > 0 and row[0] != None):
            lastStoreRev = int(row[0])
        cur.close()
        return(lastStoreRev)

    def getFilePathId(self, filepath, updcur):
        '''
        update the filepath id if required.
        '''
        id = None
        if( filepath ):
            querycur=self.dbcon.cursor()
            querycur.execute('select id from SVNPaths where path = ?', (filepath,))
            resultrow = querycur.fetchone()
            if( resultrow == None):
                updcur.execute('INSERT INTO SVNPaths(path) values(?)', (filepath,))
                querycur.execute('select id from SVNPaths where path = ?', (filepath,))
                resultrow = querycur.fetchone()
            id = resultrow[0]
            querycur.close()
            
        return(id)
    
    def ConvertRevs(self, startrev, endrev, bUpdLineCount):
        self.printVerbose("Converting revisions %d to %d" % (startrev, endrev))
        if( startrev < endrev):
            querycur = self.dbcon.cursor()
            updcur = self.dbcon.cursor()
            logging.info("Updating revision from %d to %d" % (startrev, endrev))
            svnloglist = svnlogiter.SVNRevLogIter(self.svnclient, startrev, endrev)
            revcount = 0
            lc_updated = 'N'
            if( bUpdLineCount == True):
                lc_updated = 'Y'
            lastrevno = 0
            bAddDummy=True
            
            for revlog in svnloglist:
                logging.debug("Revision author:%s" % revlog.author)
                logging.debug("Revision date:%s" % revlog.date)
                logging.debug("Revision msg:%s" % revlog.message)
                revcount = revcount+1
                
                addedfiles, changedfiles, deletedfiles = revlog.changedFileCount()                
                if( revlog.isvalid() == True):
                    updcur.execute("INSERT into SVNLog(revno, commitdate, author, msg, addedfiles, changedfiles, deletedfiles) \
                                values(?, ?, ?, ?,?, ?, ?)",
                                (revlog.revno, revlog.date, revlog.author, revlog.message, addedfiles, changedfiles, deletedfiles))
                    for change in revlog.getDiffLineCount(bUpdLineCount):
                        filename = change.filepath_unicode()
                        changetype = change.change_type()
                        linesadded = change.lc_added()
                        linesdeleted = change.lc_deleted()
                        copyfrompath,copyfromrev = change.copyfrom()
                        entry_type = 'R' #Real log entry.
                        pathtype = change.pathtype()
                        if(pathtype=='D'):
                            assert(filename.endswith('/')==True)
                        changepathid = self.getFilePathId(filename, updcur)
                        copyfromid = self.getFilePathId(copyfrompath,updcur)
                        updcur.execute("INSERT into SVNLogDetail(revno, changedpathid, changetype, copyfrompathid, copyfromrev, \
                                            linesadded, linesdeleted, lc_updated, pathtype, entrytype) \
                                    values(?, ?, ?, ?,?,?, ?,?,?,?)", (revlog.revno, changepathid, changetype, copyfromid, copyfromrev, \
                                            linesadded, linesdeleted, lc_updated, pathtype, entry_type))

                        if( bUpdLineCount == True and bAddDummy==True):
                            #dummy entries may add additional added/deleted file entries.
                            (addedfiles1, deletedfiles1) = self.addDummyLogDetail(change,revlog.revno, querycur,updcur)
                            addedfiles = addedfiles+addedfiles1
                            deletedfiles = deletedfiles+deletedfiles1
                            updcur.execute("UPDATE SVNLog SET addedfiles=?, deletedfiles=? where revno=?",(addedfiles,deletedfiles,revlog.revno))
                            
                        #print "%d : %s : %s : %d : %d " % (revlog.revno, filename, changetype, linesadded, linesdeleted)
                    lastrevno = revlog.revno                    
                    #commit after every change
                    if( revcount % 10 == 0):
                        self.dbcon.commit()                        
                logging.debug("Number revisions converted : %d (Rev no : %d)" % (revcount, lastrevno))
                self.printVerbose("Number revisions converted : %d (Rev no : %d)" % (revcount, lastrevno))

            if( self.verbose == False):            
                print "Number revisions converted : %d (Rev no : %d)" % (revcount, lastrevno)
            querycur.close()
            updcur.close()    
            
    def __addDummyAdditionDetails(self, change, revno, querycur, updcur):
        assert(change.change_type() == 'A')
        assert(change.isDirectory() == True)
        
        copyfrompath, copyfromrev = change.copyfrom()
        changedpath = change.filepath()
        assert(changedpath.endswith('/'))
        
        addedfiles  = 0
        entry_type = 'D'
        lc_updated = 'Y'
        changetype = 'A'
        
        path_type = 'U' #set path type to unknown
        if(copyfrompath != None):
            logging.debug("Updating addition entries")
            #the data is copied from an existing source path. and make sure
            #that we create dummy entries for files which are not already deleted
            #from the 'copy from path'
            #get list of all files in the directory at this point. It is very difficult
            #to correctly determine this list from the information already available in the
            #sqlite database. (for example, some files may be already deleted from the
            # source or they are deleted during the commiting this change). Hence
            # its better to query the file list valid for this repository, then
            #query the linecount for these files only to create the dummy entries
            
            for changepathentry in self.svnclient.getUnmodifiedFileList(changedpath, revno):
                logging.debug("changed path entry : %s" % changepathentry)
                original_path = changepathentry.replace(changedpath,copyfrompath,1)
                logging.debug('original path %s' %original_path)
                querycur.execute("select sum(linesadded), sum(linesdeleted) from SVNLogDetailVw \
                where changedpath == ? and revno < ? group by changedpath",
                    (original_path, copyfromrev))

                row = querycur.fetchone()
                if row == None:
                    continue
                #set lines added to current line count
                lc_added = row[0]-row[1]
                if( lc_added < 0):
                    lc_added = 0
                #set the lines deleted = 0
                lc_deleted = 0
                filename = svnlogiter.normurlpath(changepathentry)
                path_type = 'F'                        
                changedpathid = self.getFilePathId(changepathentry, querycur)
                copyfrompathid = self.getFilePathId(original_path, querycur)
                assert(path_type != 'U')
                updcur.execute("INSERT into SVNLogDetail(revno, changedpathid, changetype, copyfrompathid, copyfromrev, \
                                        linesadded, linesdeleted, entrytype, pathtype, lc_updated) \
                                values(?, ?, ?, ?,?,?, ?,?,?,?)", (change.revno, changedpathid, changetype, copyfrompathid, copyfromrev, \
                                        lc_added, lc_deleted, entry_type,path_type,lc_updated))
                addedfiles = addedfiles+1                    
        logging.debug("dummy add entries : %d" % addedfiles)
        return addedfiles
    
    def __addDummyDeletionDetails(self, change, revno, querycur, updcur):
        #data is deleted and possibly original path is a copied from another source.                
        assert(change.isDirectory() == True)
        assert(change.pathtype() == 'D')
        assert(change.change_type() == 'D')
            
        copyfrompath, copyfromrev = change.copyfrom()
        changedpath = change.filepath()
        assert(changedpath.endswith('/'))
            
        deletedfiles = 0
        #get list of all files in the directory at this point. It is very difficult
        #to correctly determine this list from the information already available in the
        #sqlite database. (for example, some files may be already deleted from the
        # source or they are deleted during the commiting this change). Hence
        # its better to query the file list valid for this repository, then
        #query the linecount for these files only to create the dummy entries
        changedpath = change.prev_filepath()
        revno = change.prev_revno()
        entry_type = 'D'
        lc_updated = 'Y'
        changetype = 'D'
        
        entrylist = self.svnclient.getUnmodifiedFileList(changedpath, revno)
                        
        for changepathentry in entrylist:
            querycur.execute('select sum(linesadded), sum(linesdeleted) from SVNLogDetailVw \
                        where changedpath == ? and revno < ? \
                        group by changedpath',(changepathentry, change.revno))
        
            row = querycur.fetchone()
            if row == None:
                continue
            #set lines deleted to current line count
            lc_deleted = row[1]-row[0]
            if( lc_deleted < 0):
                lc_deleted = 0
            #set lines added to 0
            lc_added = 0
            path_type = 'F'
            changetype = 'D'
            assert(path_type != 'U')
            changedpathid = self.getFilePathId(row[0], updcur)
            copyfrompathid = self.getFilePathId(copyfrompath, updcur)
            updcur.execute("INSERT into SVNLogDetail(revno, changedpathid, changetype, copyfrompathid, copyfromrev, \
                                    linesadded, linesdeleted, entrytype, pathtype, lc_updated) \
                            values(?, ?, ?, ?,?,?, ?,?,?,?)", (change.revno, changedpathid, changetype, copyfrompathid, copyfromrev, \
                                    lc_added, lc_deleted, entry_type,path_type,lc_updated))
            deletedfiles = deletedfiles+1
        return deletedfiles
        
    def addDummyLogDetail(self,change,revno, querycur, updcur):
        '''
        add dummy log detail entries for getting the correct line count data in case of tagging/branching and deleting the directories.
        '''
        
        changetype = change.change_type()        
        addedfiles = 0
        deletedfiles = 0
        #Path type is directory then dummy entries are required. For file type, 'real' entries will get creaetd                
        if( (changetype == 'D' or changetype=='A') and change.isDirectory()):
            #since we may have to query the existing data. Commit the changes first.
            self.dbcon.commit()
            print "updatng dummy linecount entries"
            
            if( changetype == 'A'):
                addedfiles= self.__addDummyAdditionDetails(change,revno, querycur, updcur)
                            
            elif( changetype == 'D'):
                deletedfiles = self.__addDummyDeletionDetails(change,revno, querycur, updcur)
                
        return(addedfiles, deletedfiles)
            
    def UpdateLineCountData(self):
        self.initdb()
        try:        
            self.__updateLineCountData()
        except Exception, expinst:            
            logging.exception("Error %s" % expinst)
            print "Error %s" % expinst            
        self.closedb()
        
    def __updateLineCountData(self):
        '''Update the line count data in SVNLogDetail where lc_update flag is 'N'.
        This function is to be used with incremental update of only 'line count' data.
        '''
        #first create temporary table from SVNLogDetail where only the lc_updated status is 'N'
        #Set the autocommit on so that update cursor inside the another cursor loop works.
        self.dbcon.isolation_level = None
        cur = self.dbcon.cursor()        
        cur.execute("CREATE TEMP TABLE IF NOT EXISTS LCUpdateStatus \
                    as select revno, changedpath, changetype from SVNLogDetail where lc_updated='N'")
        self.dbcon.commit()
        cur.execute("select revno, changedpath, changetype from LCUpdateStatus")
                
        for revno, changedpath, changetype in cur:
            linesadded =0
            linesdeleted = 0
            self.printVerbose("getting diff count for %d:%s" % (revno, changedpath))
            
            linesadded, linesdeleted = self.svnclient.getDiffLineCountForPath(revno, changedpath, changetype)
            sqlquery = "Update SVNLogDetail Set linesadded=%d, linesdeleted=%d, lc_updated='Y' \
                    where revno=%d and changedpath='%s'" %(linesadded,linesdeleted, revno,changedpath)
            self.dbcon.execute(sqlquery)            
        
        cur.close()
        self.dbcon.commit()
        
    def CreateTables(self):
        cur = self.dbcon.cursor()
        cur.execute("create table if not exists SVNLog(revno integer, commitdate timestamp, author text, msg text, \
                            addedfiles integer, changedfiles integer, deletedfiles integer)")
        cur.execute("create table if not exists SVNLogDetail(revno integer, changedpathid integer, changetype text, copyfrompathid integer, copyfromrev integer, \
                    pathtype text, linesadded integer, linesdeleted integer, lc_updated char, entrytype char)")
        cur.execute("CREATE TABLE IF NOT EXISTS SVNPaths(id INTEGER PRIMARY KEY AUTOINCREMENT, path text)")
        try:
                #create VIEW IF NOT EXISTS was not supported in default sqlite version with Python 2.5
                cur.execute("CREATE VIEW SVNLogDetailVw AS select SVNLogDetail.*, ChangedPaths.path as changedpath, CopyFromPaths.path as copyfrompath \
                    from SVNLogDetail LEFT JOIN SVNPaths as ChangedPaths on SVNLogDetail.changedpathid=ChangedPaths.id \
                    LEFT JOIN SVNPaths as CopyFromPaths on SVNLogDetail.copyfrompathid=CopyFromPaths.id")
        except:
                #you will get an exception if the view exists. In that case nothing to do. Just continue.
                pass
        #lc_updated - Y means line count data is updated.
        #lc_updated - N means line count data is not updated. This flag can be used to update
        #line count data later        
        cur.execute("CREATE INDEX if not exists svnlogrevnoidx ON SVNLog (revno ASC)")
        cur.execute("CREATE INDEX if not exists svnlogdtlrevnoidx ON SVNLogDetail (revno ASC)")
        cur.execute("CREATE INDEX IF NOT EXISTS svnpathidx ON SVNPaths (path ASC)")
        self.dbcon.commit()
        
        #Table structure is changed slightly. I have added a new column in SVNLogDetail table.
        #Use the following sql to alter the old tables
        #ALTER TABLE SVNLogDetail ADD COLUMN lc_updated char
        #update SVNLogDetail set lc_updated ='Y' ## Use 'Y' or 'N' as appropriate.

        #because of some bug in old code sometimes path contains '//' or '.'. Uncomment the line to Fix such paths
        #self.__fixPaths()
        
    def __fixPaths(self):
        '''
        because of some bug in old code sometimes the path contains '//' or '.' etc. Fix such paths
        '''
        cur = self.dbcon.cursor()
        cur.execute("select * from svnpaths")
        pathstofix = []
        for id, path in cur:
            nrmpath = svnlogiter.normurlpath(path)
            if( nrmpath != path):
                logging.debug("fixing path for %s to %s"%(path, nrmpath))
                pathstofix.append((id,nrmpath))
        for id, path in pathstofix:
            cur.execute('update svnpaths set path=? where id=?',(path, id))
        self.dbcon.commit()
        #Now fix the duplicate entries created after normalization
        cur = self.dbcon.cursor()
        updcur = self.dbcon.cursor()
        cur.execute("SELECT count(path) as pathcnt, path FROM svnpaths group by path having pathcnt > 1")
        duppathlist = [path for cnt, path in cur]
        for duppath in duppathlist:
            #query the ids for this path
            cur.execute("SELECT * FROM svnpaths WHERE path = ? order by id", (duppath,))
            correctid, duppath1 = cur.fetchone()
            print "updating path %s" % duppath
            for pathid, duppath1 in cur:
                updcur.execute("UPDATE SVNLogDetail SET changedpathid=? where changedpathid=?", (correctid,pathid))
                updcur.execute("UPDATE SVNLogDetail SET copyfrompathid=? where copyfrompathid=?", (correctid,pathid))
                updcur.execute("DELETE FROM svnpaths where id=?", (pathid,))
            self.dbcon.commit()
        #if paths are fixed. Then drop the activity hotness table so that it gets rebuilt next time.
        if( len(duppathlist) > 0):            
            updcur.execute("DROP TABLE IF EXISTS ActivityHotness")        
            self.dbcon.commit()        
            print "fixed paths"
        
    def printVerbose(self, msg):
        logging.info(msg)
        if( self.verbose==True):
            print msg            
                    
def getLogfileName(sqlitedbpath):
    '''
    create log file in using the directory path from the sqlitedbpath
    '''
    dir, file = os.path.split(sqlitedbpath)
    logfile = os.path.join(dir, 'svnlog2sqlite.log')
    return(logfile)
    
def parse_svndate(svndatestr):
    '''
    Using simple dates '{YEAR-MONTH-DAY}' as defined in http://svnbook.red-bean.com/en/1.5/svn-book.html#svn.tour.revs.dates
    '''
    svndatestr = svndatestr.strip()
    svndatestr = svndatestr.strip('{}')
    svndatestr = svndatestr.split('-')    

    year = int(svndatestr[0])
    month = int(svndatestr[1])
    day = int(svndatestr[2])

    #convert the time to typical unix timestamp for seconds after epoch
    svntime = datetime.datetime(year, month, day)
    svntime = calendar.timegm(svntime.utctimetuple())
    
    return(svntime)

def getquotedurl(url):
    '''
    svn repo url specified on the command line can contain specs, special etc. We
    have to quote them to that svn log client works on a valid url.
    '''
    import urllib
    import urlparse
    urlparams = list(urlparse.urlsplit(url, 'http'))
    urlparams[2] = urllib.quote(urlparams[2])
    
    return(urlparse.urlunsplit(urlparams))
    
def RunMain():
    usage = "usage: %prog [options] <svnrepo root url> <sqlitedbpath>"
    parser = OptionParser(usage)
    parser.set_defaults(updlinecount=False)

    parser.add_option("-l", "--linecount", action="store_true", dest="updlinecount", default=False,
                      help="extract/update changed line count (True/False). Default is False")
    parser.add_option("-g", "--log", action="store_true", dest="enablelogging", default=False,
                      help="Enable logging during the execution(True/False). Name of generate logfile is svnlog2sqlite.log.")
    parser.add_option("-v", "--verbose", action="store_true", dest="verbose", default=False,
                      help="Enable verbose output. Default is False")
    parser.add_option("-u", "--username", dest="username",default=None, action="store", type="string",
                      help="username to be used for repository authentication")
    parser.add_option("-p", "--password", dest="password",default=None, action="store", type="string",
                      help="password to be used for repository authentication")
    (options, args) = parser.parse_args()
    
    if( len(args) < 2 ):
        print "Invalid number of arguments. Use svnlog2sqlite.py --help to see the details."    
    else:
        svnrepopath = args[0]
        sqlitedbpath = args[1]
        svnrevstartdate = None
        svnrevenddate = None
        
        if( len(args) > 3):
            #more than two argument then start date and end date is specified.
            svnrevstartdate = parse_svndate(args[2])
            svnrevenddate = parse_svndate(args[3])
            
        if( not svnrepopath.endswith('/')):
            svnrepopath = svnrepopath+'/'
        
        svnrepopath = getquotedurl(svnrepopath)
        
        print "Updating the subversion log"
        print "Repository : " + svnrepopath            
        print "SVN Log database filepath : %s" % sqlitedbpath
        print "Extract Changed Line Count : %s" % options.updlinecount
        if( not options.updlinecount):
            print "\t\tplease use -l option. if you want to extract linecount information."
        if( svnrevstartdate):
            print "Repository startdate: %s" % (svnrevstartdate)
        if( svnrevenddate):
            print "Repository enddate: %s" % (svnrevenddate)
        
        if(options.enablelogging==True):
            logfile = getLogfileName(sqlitedbpath)
            logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s %(message)s',
                    filename=logfile,
                    filemode='w')
            print "Debug Logging to file %s" % logfile

        conv = None            
        conv = SVNLog2Sqlite(svnrepopath, sqlitedbpath,verbose=options.verbose, username=options.username, password=options.password)
        conv.convert(svnrevstartdate, svnrevenddate, options.updlinecount)        
        
if( __name__ == "__main__"):
    RunMain()
    
    