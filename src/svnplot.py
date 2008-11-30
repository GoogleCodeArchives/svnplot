'''
Generate various graphs from the Subversion log data in the sqlite database.
It assumes that the sqlite file is generated using the 'svnlog2sqlite.py' script.

Graph types to be supported
1. Activity by hour of day bar graph (commits vs hour of day)
2. Activity by day of week bar graph (commits vs day of week)
3. Author Activity horizontal bar graph (author vs adding+commiting percentage)
4. Commit activity for each developer - scatter plot (hour of day vs date)
5. Contributed lines of code line graph (loc vs dates). Using different colour line
   for each developer
6. total loc line graph (loc vs dates)
7. file count vs dates line graph
8. average file size vs date line graph
9. directory size vs date line graph. Using different coloured lines for each directory
10. directory size pie chart (latest status)
11. Loc and Churn graph (loc vs date, churn vs date)- Churn is number of lines touched
	(i.e. lines added + lines deleted + lines modified)
12. Repository heatmap (treemap)

--- Nitin Bhide (nitinbhide@gmail.com)

Part of 'svnplot' project
Available on google code at http://code.google.com/p/svnplot/
Licensed under the 'New BSD License'

To use copy the file in Python 'site-packages' directory Setup is not available
yet.
'''

import matplotlib.pyplot as plt
import sqlite3
import calendar

class SVNPlot:
    def __init__(self, svndbpath):
        self.svndbpath = svndbpath        
        self.dbcon = sqlite3.connect(self.svndbpath, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        #self.dbcon.row_factory = sqlite3.Row
        self.cur = self.dbcon.cursor()        

    def __del__(self):
        self.dbcon.close()
        
    def ActivityByWeekday(self, filename):
        self.cur.execute("select strftime('%w', commitdate), count(revno) from SVNLog group by strftime('%w', commitdate)")
        labels =[]
        data = []
        for dayofweek, commitcount in self.cur:
           data.append(commitcount)           
           labels.append(calendar.day_abbr[int(dayofweek)])

        ax = self.DrawBarGraph(data, labels,0.5)
        ax.set_ylabel('commits')
        ax.set_xlabel('Day of Week')
        ax.set_title('Activity By Weekday')

        fig = ax.figure                        
        fig.savefig(filename, dpi=100, format='png')        

    def ActivityByTimeOfDay(self, filename):
        self.cur.execute("select strftime('%H', commitdate), count(revno) from SVNLog group by strftime('%H', commitdate)")
        labels =[]
        data = []
        for hourofday, commitcount in self.cur:
           data.append(commitcount)           
           labels.append(int(hourofday))

        ax = self.DrawBarGraph(data, labels,0.5)
        ax.set_ylabel('commits')
        ax.set_xlabel('Time of Day')
        ax.set_title('Activity By Time of Day')

        fig = ax.figure                        
        fig.savefig(filename, dpi=100, format='png')        

    def DrawBarGraph(self, data, labels, barwid):
        #create dummy locations based on the number of items in data values
        xlocations = [x*barwid*2+barwid for x in range(len(data))]
        xtickloc = [x+barwid/2.0 for x in xlocations]
        xtickloc.append(xtickloc[-1]+barwid)
        
        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.set_xticks(xtickloc)
        ax.set_xticklabels(labels)
        ax.bar(xlocations, data, width=barwid)
        
        return(ax)
        
if(__name__ == "__main__"):
    #testing
    svndbpath = "D:\\nitinb\\SoftwareSources\\SVNPlot\\svnrepo.db"
    graphfile = "D:\\nitinb\\SoftwareSources\\SVNPlot\\graph.png"
    svnplot = SVNPlot(svndbpath)
    svnplot.ActivityByTimeOfDay(graphfile)
    