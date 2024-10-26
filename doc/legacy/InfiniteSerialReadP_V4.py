# -*- coding: utf-8 -*-

# Python 3 
# Upon startup, find and read the serial port matching the correct description. This Automatic detection
# is probably where it becomes difficult to support multiple devices on the same PC, because the JeeNode Arduino Modules 
# currently don't broadcast their ID number or Operating channel. This could be solved via a couple lines of code within the Arduino sketch. 
# then the python or labview code would need to recognize (or be told) which FTDI device it had connected to, and a system of 
# rigourous ID tracking would need to be instituted

#***************************************************************************************************************************************************
#SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*SETUP*

# Define Program Parameters and Constants
SBR = 9600 # Serial baudrate
TMO = 0.5 # Serial Connection Timeout, in seconds


# Import Libraries
import os.path
#import math
import serial
import serial.tools.list_ports
import time
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from IPython import display
from matplotlib.widgets import Button
from matplotlib.widgets import RadioButtons
import threading
import tkinter
import warnings
warnings.filterwarnings("ignore",category = matplotlib.cbook.mplDeprecation)
print("Backend =", matplotlib.backends.backend)

#Place Infinite Serial Read and "Test Files" in the same directory level, wherever that may be
File1 = "InfiniteSerialReadP_V4.py"
print("File1 =", File1)
DefaultDirectory = os.path.join(os.path.dirname(os.path.abspath(File1)),"Centrifuge Test Files")
print("DefaultDirectory = ",DefaultDirectory)

ST=time.localtime(time.time())
FileName = str("ArduinoLogFile_%s.%02d.%02d_%02d.%02d.%02d" %(ST.tm_year,ST.tm_mon,ST.tm_mday,ST.tm_hour,ST.tm_min,ST.tm_sec))

FullPath= os.path.join(DefaultDirectory, FileName+".txt")
FullPath2=os.path.join(DefaultDirectory, FileName+"c1c.txt")
LOCK1 = threading.Lock()

print("Raw Data Output File =", FullPath)

global CF
global PCBCMD

try:
    CalibrationFile = "Calibration File"
    CalibrationPath = os.path.join(DefaultDirectory, CalibrationFile+".txt")
    with open(CalibrationPath,'r') as cf:
        CF = np.loadtxt(cf,dtype = 'float',delimiter=',',skiprows= 2)
    print("Calibration Factors in Use: \n\n", CF)
    cf.close()
except FileNotFoundError:
    CF = np.array([[0.001,-0.000000106186,-0.000000106186,-0.000000106186,-0.000000106186,-0.000000106186,-0.000000106186,-0.000000106186,0.000000106186,100],[0,0,2.54,2.54,2.54,2.54,2.54,2.54,0,0]])

#**************************************************************************************************************************************************
#FILTER*FILTER*FILTER*FILTER*FILTER*FILTER*FILTER*FILTER*FILTER*FILTER*FILTER*FILTER*FILTER*FILTER*FILTER*FILTER*FILTER*FILTER*FILTER*FILTER*

# Define Filtering Function
def DataFiltering(i):
    global OUT2
    global hasdata,FilterFlag
    try:
        #LOCK1.acquire()
        #print("Removing Duplicates")
        #Remove Duplicate Recordings using a boolean mask. Mask (aka Truth list) returns true when values are not duplicate.
        (nrows,ncols) = OUT2.shape
        FilterFlag=False;
        #TLIST = np.not_equal(OUT2[1:,0] , OUT2[0:nrows-1,0])
        #TLIST = np.append(TLIST,[True])
        #OUT2 = OUT2[TLIST,:]
        
        #Remove or Suppress Outliers:
        #print("Suppressing Outliers (if any)")
        #(nrows,ncols) = OUT2.shape
        #TLIST = np.ones((nrows,),dtype='bool')
        #Filter on LVDT data and Battery Voltage, (but NOT g-level or Temperature)
        cols = [2,3,4,5,6,7,9]
        X1 = 1
        X2 = 1
        #for i in range(X1,nrows-X2):
        #for (i=ii):
        Temp = np.concatenate((OUT2[i-X1:i,cols],OUT2[i+1:i+X2+1,cols]),axis=0)
        Sigma = np.maximum(0.25,np.std(Temp,0)*3)
        print("Sigma =",Sigma)
        Mean  = np.mean(Temp,0)
        
        if (any(abs(OUT2[i,cols] - Mean) > Sigma)):
            print("REMOVING INTERPRETED BAD DATA")
            FilterFlag = True;
            #Temp2=np.concatenate((OUT2[i-1:i,:],OUT2[i+1:i+2,:]),axis=0)
            #OUT2[i,:] = np.mean(Temp2,0)
            OUT2 = np.delete(OUT2,i,axis=0)
            #TLIST[i] = not(any(abs(OUT2[i,cols] - Mean) > Sigma))
        #OUT2 = OUT2[TLIST,:]
        
        #Save Values to File:
        #try:
        #   with open(FullPath2,'a+') as f2:
        #        (nrows,ncols) = OUT2.shape
        #        HeaderLine = str('''TimeStamp, TEMP (16b), S1 (16b), S2 (16b), S3 (16b), S4 (16b), S5 (16b), S6 (16b), G (16b), BAT (V*100) \n ''')
        #        f2.write(HeaderLine)
        #        #for i in range(0,nrows):
        #        for i:
        #            OUT_S = str('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' 
        #                                %(OUT2[i,0], OUT2[i,1],OUT2[i,2],OUT2[i,3],OUT2[i,4],OUT2[i,5],OUT2[i,6],OUT2[i,7],OUT2[i,8],OUT2[i,9]))
        #            f2.write(OUT_S)
        #        f2.close()
        #        
                
        #except FileNotFoundError:
        #    print("Save-To File Not Found")
        hasdata = True
    finally:
        #LOCK1.release()
        print("Filtering Complete")
    
    
#***************************************************************************************************************************************************
#INITIALIZE*INITIALIZE*INITIALIZE*INITIALIZE*INITIALIZE*INITIALIZE*INITIALIZE*INITIALIZE*INITIALIZE*INITIALIZE*INITIALIZE*INITIALIZE*

def InitializeValues():
    global updatetoggle,runtoggle,hasdata,unprocessed,EndFlag,FilterFlag
    global OUTRAW,OUTFILT,OUT2,CF,by1
    global PCBCMD
    
    OUT2 = np.empty((1,10),dtype=float)

    by1 = (np.array(range(0,10))*8)
    OUTRAW = np.zeros((1,10))
    OUTFILT = np.zeros((1,10))
    
    runtoggle = True
    unprocessed = True
    hasdata = False
    EndFlag = False
    FilterFlag = False
#***************************************************************************************************************************************************
#PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*PLOT*


#Define Plotting Loop
def PlotLoop():
    global updatetoggle,runtoggle,hasdata,unprocessed,EndFlag
    global OUTFILT,OUT2,CF,by1
    global PCBCMD
    
    #OUT2 = np.empty((1,10),dtype=float)
    
    #by1 = (np.array(range(0,10))*8)
    #OUTFILT = np.zeros((1,10))
    
    #runtoggle = True
    #unprocessed = True
    #hasdata = False
    #EndFlag = False
    InitializeValues()
    #print("EndFlag =",EndFlag)
    
# Define Button Options:
    class Toggle(object):
        ind = True
        
        def stoprun(self,event):
            global runtoggle
            self.ind = False
            runtoggle = False
            print('Stopping Data Collection...')
        
        #def process(self,event):
        #    self.ind = False
        #    button_click(self)
            
        def appfinish(self,event):
            global EndFlag
            print('Finished')
            EndFlag = True
        
        def loglabel(self,event):
            try:
                self.ind = not(self.ind)
                if self.ind:
                    ax1.set_xscale('linear')
                    bscale.label.set_text('Axis:\nLinear')
                else:
                    ax1.set_xscale('log')
                    bscale.label.set_text('Axis:\nLog')
            except:
                print('some error occurred')
                
        def Calibrate(self,event):
            try: 
                global PCBCMD
                PCBCMD = 's101'+PCBCMD[-1]
                bReadSensors.active = True
                bEndCalibration.active = True
                bReadSensors.color = (0,0.5,0.1)
                bEndCalibration.color = (0,0.5,0.1)
                bReadSensors.hovercolor = (0,0.6,0.15)
                bEndCalibration.hovercolor = (0,0.6,0.15)
            except:
                print('some error occurred')
                
        def ReadSensors(self,event):
            try:
                global PCBCMD
                PCBCMD = 's111'+PCBCMD[-1]
            except:
                print('some error occurred')
                
        def EndCalibration(self,event):
            try:
                global PCBCMD,bReadSensors,bEndCalibration
                PCBCMD = 's001'+PCBCMD[-1]
                bReadSensors.color = bnc1
                bEndCalibration.color = bnc1
                bReadSensors.hovercolor = bnc1
                bEndCalibration.hovercolor = bnc1
                plt.draw()
                plt.pause(0.5)
                plt.draw()
                bReadSensors.active = False
                bEndCalibration.active = False
            except:
                print('some error occurred')
        def ReadingSchedule(self,event):
            try:
                global PCBCMD
                
                Reading_Dict = {'Slow':'1','Normal':'2','Fast':'3'}
                print(event)
                PCBCMD = PCBCMD[:3]+'1'+Reading_Dict[event]
            except:
                print("Some Error Occurred")
                
        #def Filter(self,event):
        #    try:
        #        global OUT2
        #        filterthread = threading.Thread(target = DataFiltering)
        #        filterthread.start()
        #    except:
        #        print("Some Error Occurred...")
                
        def Manual(self,event):
            try:
                global updatetoggle
                self.ind = not(updatetoggle)
                updatetoggle = self.ind
                if self.ind:
                    bManual.label.set_text('View:\nAuto')
                    plt.sca(ax3)
                    plt.ylim((BOT_VALUE,FULL_VALUE))
                    ax1.relim();
                    ax2.relim();
                    ax3.relim()
                    ax1.autoscale()
                    ax2.autoscale()
                    ax3.autoscale(tight=True,axis='x') 
                    plt.draw()
                else:
                    bManual.label.set_text('View:\nUser')
                    plt.draw()
            except:
                print("Some Error Occurred")
                
        def StartTest(self,event):
            try:
                run_thread = threading.Thread(target=ReadLoop)
                run_thread.start()
            except:
                print("Some Error Occurred")
                
        def LoadData(self,event):
            try:
                load_thread = threading.Thread(target=LoadDataLoop)
                load_thread.start()
            except:
                print("Some Error Occurred")


    
    fig, (ax1, ax2, ax3) = plt.subplots(3,1,sharex=True)  
    plt.xlabel('Time (Minutes)')  
    ax1.set_ylabel('Sensor Position (cm)')
    ax2.set_ylabel('G-Level')
    ax3.set_ylabel('Battery Voltage (V)')
    ax1.grid(which='minor',color=(0,0,0),linestyle = ':',linewidth = 0.5)
    ax2.grid(which='minor',color=(0,0,0),linestyle = ':',linewidth = 0.5)
    ax3.grid(which='minor',color=(0,0,0),linestyle = ':',linewidth = 0.5)
    
    ax1.grid(which='major',color=(0,0,0),linestyle = '-',linewidth = 0.5)
    ax2.grid(which='major',color=(0,0,0),linestyle = '-',linewidth = 0.5)
    ax3.grid(which='major',color=(0,0,0),linestyle = '-',linewidth = 0.5)
    
    fig.suptitle('Centrifuge Swell Test: \n'+FileName)
    # Color Palette for Plotting:
    bnc1 = (0.85,0.85,0.85) #(0.93,0.9,0.75)
    bnc2 = (0.95,0.95,0.95)
    
    FC1 = (0.93,0.9,0.75) 
    FC2 = (0.63,0.6,0.45) 
    figfacecolor = (0.7,0.7,0.7)
    #plt.rcParams['axes.facecolor'] = figfacecolor
    plt.rcParams['savefig.facecolor'] = figfacecolor
    fig.set_facecolor(color=figfacecolor)
    ax1.set_facecolor(color=FC1);ax2.set_facecolor(color=FC1);ax3.set_facecolor(color=FC1)

    L1, = ax1.plot(OUTFILT[:,0],OUTFILT[:,2], color=(0.1,0.3,0.8,1),marker = 'o', label = 'LVDT 1')
    L2, = ax1.plot(OUTFILT[:,0],OUTFILT[:,3], color=(0,0.5,0.8,1),marker = 'd', label = 'LVDT 2')
    L3, = ax1.plot(OUTFILT[:,0],OUTFILT[:,4], color=(0.7,0.4,0,1),marker = '<', label = 'LVDT 3')
    L4, = ax1.plot(OUTFILT[:,0],OUTFILT[:,5], color=(0.8,0.6,0,1),marker = '>', label = 'LVDT 4')
    L5, = ax1.plot(OUTFILT[:,0],OUTFILT[:,6], color=(0.2,0.2,0.2,1),marker = '*', label = 'LVDT 5')
    L6, = ax1.plot(OUTFILT[:,0],OUTFILT[:,7], color=(0.5,0.5,0.5,1),marker = 'p', label = 'LVDT 6')
    plt.sca(ax1)
    plt.legend(handles=[L1,L2,L3,L4,L5,L6],bbox_to_anchor=(0., 1.02, 1., .102), loc=3,
           ncol=6, mode="expand", borderaxespad=0,facecolor=FC1,edgecolor=FC2,framealpha = 1,shadow=True)
    
    L7, = ax2.plot(OUTFILT[:,0],OUTFILT[:,8], color=(0.8,0.2,0.2,1), label = 'G-level')
    plt.sca(ax2)
    plt.legend(handles=[L7],bbox_to_anchor=(0., 1.02, 1., .102), loc=3,
           ncol=1, mode="expand", borderaxespad=0,facecolor=FC1,edgecolor=FC2,framealpha = 1,shadow=True)
    
    
    
    L8, = ax3.plot(OUTFILT[:,0],OUTFILT[:,9], color=(0,0,0,1), label = 'Battery Voltage')
    plt.sca(ax3)
    plt.legend(handles=[L8],bbox_to_anchor=(0., 1.02, 1., .102), loc=3,
           ncol=1, mode="expand", borderaxespad=0,facecolor=FC1,edgecolor=FC2,framealpha = 1,shadow=True)
    
    XMAX = 2 #max(OUTFILT(:,0))
    BOT_VALUE = 3.0
    LOW_VALUE = 3.4
    MID_VALUE = 3.8
    FULL_VALUE = 5.0
    
    LOW_BATT = np.array([[0,BOT_VALUE],[0,LOW_VALUE],[XMAX,LOW_VALUE],[XMAX,BOT_VALUE]])
    MID_BATT = np.array([[0,LOW_VALUE],[0,MID_VALUE],[XMAX,MID_VALUE],[XMAX,LOW_VALUE]])
    FULL_BATT = np.array([[0,MID_VALUE],[0,FULL_VALUE],[XMAX,FULL_VALUE],[XMAX,MID_VALUE]])
    
    
    L8LOW = matplotlib.patches.Polygon(LOW_BATT,closed=True,edgecolor=[0.861,0.63,0.525],facecolor='none',hatch='/////|||',linewidth = 1,linestyle = '-')
    L8MID = matplotlib.patches.Polygon(MID_BATT,closed=True,edgecolor=[0.861,0.84,0.525],facecolor='none',hatch='////|||',linewidth = 1,linestyle = '-')
    L8FULL = matplotlib.patches.Polygon(FULL_BATT,closed=True,edgecolor=[0.651,0.84,0.525],facecolor='none',hatch='///|||',linewidth = 1,linestyle = '-')
    
    #L8LOW = ax3.fill(LOW_BATT[:,0],LOW_BATT[:,1],closed=True,color=[0.5,0,0])
    #L8MID = ax3.fill(MID_BATT[:,0],MID_BATT[:,1],closed=True,color=[0.5,0.5,0])
    #L8FULL = ax3.fill(FULL_BATT[:,0],FULL_BATT[:,1],closed=True,color=[0,0.5,0])
    ax3.add_patch(L8LOW)
    ax3.add_patch(L8MID)
    ax3.add_patch(L8FULL)
    plt.sca(ax3)
    plt.ylim((BOT_VALUE,FULL_VALUE))
    ax1.relim();
    ax2.relim();
    ax3.relim()
    ax1.autoscale()
    ax2.autoscale()
    ax3.autoscale(tight=True,axis='x') 
    
    plt.subplots_adjust(bottom = 0.1, top = 0.9, left = 0.1, hspace = 0.25, right = 0.9)
    
    callback = Toggle()
    
    axCalibrate      = plt.axes([0.91,0.85,0.08,0.075])
    axReadSensors    = plt.axes([0.91,0.77,0.08,0.075])
    axEndCalibration = plt.axes([0.91,0.69,0.08,0.075])
    axLoadData       = plt.axes([0.91,0.61,0.08,0.075])
    axReadingSchedule= plt.axes([0.91,0.45,0.08,0.15],facecolor = bnc1)
    

    axscales         = plt.axes([0.91,0.37,0.0375,0.075])
    axManual         = plt.axes([0.9525,0.37,0.0375,0.075])
    
    #axFilter         = plt.axes([0.91,0.1,0.0375,0.075])
    axStartTest          = plt.axes([0.91,0.28,0.08,0.075])
    axstop           = plt.axes([0.91,0.2,0.08,0.075])
    axfinish         = plt.axes([0.91,0.1,0.08,0.075])
    

    
    bstop            = Button(axstop,'Stop \nCollection',color=bnc1,hovercolor=bnc2)
    bstop.on_clicked(callback.stoprun)
    
    bprocess         = Button(axfinish,'Finish \nTest',color=bnc1,hovercolor=bnc2)
    bprocess.on_clicked(callback.appfinish)
    
    bscale           = Button(axscales,'Axis:\nLinear',color=bnc1,hovercolor=bnc2)
    bscale.on_clicked(callback.loglabel)
    
    bCalibrate       = Button(axCalibrate,'Start \n Calibration',color =bnc1,hovercolor=bnc2)
    bCalibrate.on_clicked(callback.Calibrate)
    

    bReadSensors     = Button(axReadSensors,'Calibration \n Reading',color = bnc1,hovercolor=bnc2)
    bReadSensors.on_clicked(callback.ReadSensors)
    
    bEndCalibration  = Button(axEndCalibration,'Finish \n Calibration',color = bnc1,hovercolor=bnc2)
    bEndCalibration.on_clicked(callback.EndCalibration)
    
    bReadingSchedule = RadioButtons(axReadingSchedule,('Slow','Normal','Fast'),activecolor = (0,0.5,0.8),active = 1)
    bReadingSchedule.on_clicked(callback.ReadingSchedule)
    
    #bFilter = Button(axFilter,'Filter \nData',color = bnc1,hovercolor = bnc2)
    #bFilter.on_clicked(callback.Filter)
    
    bManual = Button(axManual,'View:\nAuto',color = bnc1,hovercolor = bnc2)
    bManual.on_clicked(callback.Manual)
    updatetoggle = True
    
    bStartTest = Button(axStartTest,'Start Test',color = bnc1,hovercolor=bnc2)
    bStartTest.on_clicked(callback.StartTest)
    
    bLoadData = Button(axLoadData,'Load Data',color = bnc1, hovercolor=bnc2)
    bLoadData.on_clicked(callback.LoadData)
    
    #Initialize Button States:
    bCalibrate.active = True
    bReadSensors.active = False
    bEndCalibration.active = False
    
    # Show Plot:
    plt.ion()
    while runtoggle:
        if hasdata:
            try:
                LOCK1.acquire()
                L1.set_ydata(OUT2[1:,2]); L1.set_xdata(OUT2[1:,0])
                L2.set_ydata(OUT2[1:,3]); L2.set_xdata(OUT2[1:,0])
                L3.set_ydata(OUT2[1:,4]); L3.set_xdata(OUT2[1:,0])
                L4.set_ydata(OUT2[1:,5]); L4.set_xdata(OUT2[1:,0])
                L5.set_ydata(OUT2[1:,6]); L5.set_xdata(OUT2[1:,0])
                L6.set_ydata(OUT2[1:,7]); L6.set_xdata(OUT2[1:,0])
                L7.set_ydata(OUT2[1:,8]); L7.set_xdata(OUT2[1:,0])
                L8.set_ydata(OUT2[1:,9]); L8.set_xdata(OUT2[1:,0])
                
                XMAX = (OUT2[-1,0]+1)*1.05
                LOW_BATT = np.array([[0,BOT_VALUE],[0,LOW_VALUE],[XMAX,LOW_VALUE],[XMAX,BOT_VALUE]])
                MID_BATT = np.array([[0,LOW_VALUE],[0,MID_VALUE],[XMAX,MID_VALUE],[XMAX,LOW_VALUE]])
                FULL_BATT = np.array([[0,MID_VALUE],[0,FULL_VALUE],[XMAX,FULL_VALUE],[XMAX,MID_VALUE]])
                
                L8LOW.set_xy(LOW_BATT)
                L8MID.set_xy(MID_BATT)
                L8FULL.set_xy(FULL_BATT)
                
                if updatetoggle:
                    plt.sca(ax3)
                    plt.ylim((BOT_VALUE,FULL_VALUE))
                    ax1.relim();
                    ax2.relim();
                    ax3.relim()
                    ax1.autoscale()
                    ax2.autoscale()
                    ax3.autoscale(tight=True,axis='x') 
                    
                plt.draw()
                hasdata = False
                #print('3. runtoggle =',runtoggle)
            finally:
                LOCK1.release()
        else:
            #This line is important for program "responsiveness"
            plt.pause(0.2)
    while not(EndFlag) and unprocessed:
        plt.pause(1)
            
#***************************************************************************************************************************************************
#READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ*READ

# Define Serial Port ReadLoop
def ReadLoop():
    global updatetoggle,runtoggle,hasdata,unprocessed,EndFlag,FilterFlag
    global OUTRAW,OUTFILT,OUT2,CF,by1
    global PCBCMD
    
    InitializeValues()
    
    try:
        #print(serial.tools.list_ports.comports())
        # ftdi=next(serial.tools.list_ports.grep("FTDI")) # Old line to search for FTDI device, when "FTDI" was part of the hardware ID
        ftdi=next(serial.tools.list_ports.grep("VID:PID=0403:6001"))
        print("\nftdi =",ftdi)
        ser = serial.Serial()
        ser.baudrate = SBR
        ser.port = ftdi[0]
        ser.timeout = TMO
        print("Serial Port to use:",ser.port)
        ser.close()
        if ser.isOpen() == False:
            f_raw = open(FullPath, "a+")  # Open/Create file for Appending (a+ mode)
            f_filt = open(FullPath2, "a+")  # Open/Create file for Appending (a+ mode)
            HeaderLine = str('''TimeStamp, TEMP (16b), S1 (16b), S2 (16b), S3 (16b), S4 (16b), S5 (16b), S6 (16b), G (16b), BAT (V*100) \n ''')
            HeaderLine2 = str('''TimeStamp, S1 (cm), S2 (cm), S3 (cm), S4 (cm), S5 (cm), S6 (cm), G (g's) \n ''')
            f_raw.write(HeaderLine)
            f_filt.write(HeaderLine2)
            
            PCBCMD = 's0001'
            
            print('\nOpening Serial Port:')
            ser.open();
            print('--Successful'); print('\nWaiting to Receive Data:')
            STI = time.time()
            
            while runtoggle:
                #res=ser.read(ser.inWaiting() or 1)
                #print("1")
                #time.sleep(50) # Sleep 50 seconds, then wakeup        
                #print(ser.isOpen())
                #OUT = ser.readline()
                OUT = ser.readline()
                ser.reset_input_buffer()
                if (type(OUT)==bytes) & (len(OUT)>0):
                    #ST = time.localtime(time.time())              # Create date time for file
                    ST1 = (time.time()-STI)/60                    # Create Now time for Plotting (minutes)
                    #TSTAMP = str("%s.%02d.%02d_%02d.%02d.%02d" %(ST.tm_year,ST.tm_mon,ST.tm_mday,ST.tm_hour,ST.tm_min,ST.tm_sec))
                    #ser.close()
                    #print(ser.isOpen())
                    #print(OUT)
                    try:         # Convert and Append data to file
                        OUTRAW[0,0] = ST1
                        for b in range(1,10):
                            OUTRAW[0,b] = int(OUT[by1[b-1]:by1[b]],16)
                        
                        # *************  APPLY CALIBRATION FACTORS **************************************
                        
                        for b in range(1,10):
                            OUTFILT[0,b] = (float(OUTRAW[0,b])*float(CF[0,b]))+CF[1,b]
                            #print("CF = ",CF[0,b-1])
                        
                        Idx1 = (0,1)
                        for b in Idx1:
                            OUTFILT[0,b] = OUTRAW[0,b]
                        # ********************************************************************************
                        
                        # Raw Output:
                        OUT1 = str('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' 
                                %(OUTRAW[0,0], OUTRAW[0,1],OUTRAW[0,2],OUTRAW[0,3],OUTRAW[0,4],OUTRAW[0,5],OUTRAW[0,6],OUTRAW[0,7],OUTRAW[0,8],OUTRAW[0,9]))
                        
                        try:
                            LOCK1.acquire()
                            OUT2 = np.concatenate((OUT2,OUTFILT),axis=0) 
                            (rows,cols) = OUT2.shape
                            ii=rows-2
                            if (ii>=1):
                                #ii = rows-2
                                #filterthread = threading.Thread(target = DataFiltering(ii))
                                #filterthread.start()
                                DataFiltering(ii)
                                
                            if (ii>=1 and not FilterFlag):
                                OUT3 = str('%s, %s, %s, %s, %s, %s, %s, %s \n' 
                                    %(OUT2[ii,0]/60,OUT2[ii,2],OUT2[ii,3],OUT2[ii,4],OUT2[ii,5],OUT2[ii,6],OUT2[ii,7],OUT2[ii,8]))
                                f_filt.write(OUT3)                           
                            
                            hasdata = True
                        finally:
                            LOCK1.release()
                        
                        # Write File after converting Data:
                        f_raw.write(OUT1) 
                        print('***** Conversion Successful *****')
                        print('Data Out =', OUT2[rows-1,:])
                        print('***** Value Saved to File *****')
                        # Close/Reopen to ensure Data saved to file properly
                        f_raw.close()
                        f_raw = open(FullPath, "a+")
                        f_filt.close()
                        f_filt = open(FullPath2, "a+")
                    except (IndexError,ValueError):  # Write Down Anyways
                        print('--Converting to Number Failed--') 
                        OUT1 = str(' %s \n' %(OUT))
                        print(OUT1)
                        print('--Value Not Saved to File--')
                
                if (PCBCMD[3] == '1'):
                # Write and reset Send Flag
                    print("Sending Command to PCB")
                    print(PCBCMD)
                    plt.pause(0.01)
                    ser.write(PCBCMD.encode('utf-8'))
                    # Reset "Valid to Send Data" Flag:
                    PCBCMD = PCBCMD[:3]+'0'+PCBCMD[-1]
                    print(PCBCMD)
                    
                
                
            # Close File after all data is recorded:    
            f_raw.close()
            f_filt.close()
            print('Data Saved to:', FileName)
            ser.close()
            print('Serial Port Successfully Closed')
            print('Data Read Loop Now Exiting')
            print('Please Click "Finish" to Exit Program')
            #wait = input('PRESS ANY BUTTON TO EXIT')
            #EndFlag = True;
        else:          
            print("Serial Port Unavailable; try closing other programs that may be using this serial port \n Then close This program and try again")
            input("PRESS ANY BUTTON TO EXIT")
        
    except StopIteration:
        print("\n\n NO FTDI DEVICE CONNECTED. \n Please Close this Program, connect A JeeNode and try again \n\n")
        input(" PRESS ANY BUTTON TO EXIT")
    
    except serial.SerialException:
        print("\n\n SERIAL (USB) PORT UNAVAILABLE; \n Try closing other programs using this port \n Then close this program and try again \n\n")
        input(" PRESS ANY BUTTON TO EXIT")
    
    
    
def LoadDataLoop():
    global updatetoggle,runtoggle,hasdata,unprocessed,EndFlag
    global OUTRAW,OUTFILT,OUT2,CF,by1
    global PCBCMD
    
    InitializeValues()
    
    #InFile = tkinter.filedialog.askopenfilename()
    
    
    
plot_thread = threading.Thread(target=PlotLoop)
plot_thread.start()


# 
# ports = list(serial.tools.list_ports.comports())
# for i in ports:
#    print(i)