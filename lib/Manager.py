# -*- coding: utf-8 -*-
from util import configfile
import time, sys, atexit
from PyQt4 import QtCore, QtGui
from DataManager import *

class Manager():
    """Manager class is responsible for:
      - Loading/configuring device modules and storing their handles
      - Managing the device rack GUI
      - Creating protocol task handles
      - Loading interface modules and storing their handles
      - Creating and managing DirectoryHandle objects
      - Providing unified timestamps
      - Making sure all devices/modules are properly shut down at the end of the program"""
    
    def __init__(self, configFile=None):
        self.alreadyQuit = False
        atexit.register(self.quit)
        self.devices = {}
        self.modules = {}
        self.devRack = None
        self.dataManager = None
        self.readConfig(configFile)
        if 'win' in sys.platform:
            time.clock()  ### Required to start the clock in windows
            self.startTime = time.time()
            self.time = self.winTime
        else:
            self.time = self.unixTime

    def readConfig(self, configFile):
        """Read configuration file, create device objects, add devices to list"""
        print "============= Starting Manager configuration from %s =================" % configFile
        cfg = configfile.readConfigFile(configFile)
        if not cfg.has_key('devices'):
            raise Exception('configuration file %s has no "devices" section.' % configFile)
        for k in cfg['devices']:
            print "\n=== Configuring device %s ===" % k
            conf = None
            if cfg['devices'][k].has_key('config'):
                conf = cfg['devices'][k]['config']
            modName = cfg['devices'][k]['module']
            self.loadDevice(modName, conf, k)
        if 'users' in cfg:
            user = 'Luke'
            baseDir = cfg['users'][user]['storageDir']
            self.dataManager = DataManager(self, baseDir)
        else:
            raise Exception("No configuration found for data management!")
        print "\n============= Manager configuration complete =================\n"



    def __del__(self):
        self.quit()
    
    def loadDevice(self, modName, conf, name):
        mod = __import__('lib.devices.%s.interface' % modName, fromlist=['*'])
        devclass = getattr(mod, modName)
        self.devices[name] = devclass(self, conf, name)
        return self.devices[name]
    
    def getDevice(self, name):
        if name not in self.devices:
            raise Exception("No device named %s" % name)
        return self.devices[name]

    def loadModule(self, module, name, config={}):
        mod = __import__('lib.modules.%s.interface' % module, fromlist=['*'])
        modclass = getattr(mod, module)
        self.modules[name] = modclass(self, name, config)
        return self.modules[name]
        
    def getModule(self, name):
        if name not in self.modules:
            raise Exception("No module named %s" % name)
        return self.modules[name]
        
    def winTime(self):
        """Return the current time in seconds with high precision (windows version, use Manager.time() to stay platform independent)."""
        return time.clock() + self.startTime
    
    def unixTime(self):
        """Return the current time in seconds with high precision (unix version, use Manager.time() to stay platform independent)."""
        return time.time()
    
    def runProtocol(self, cmd):
        t = Task(self, cmd)
        t.execute()
        return t.getResult()

    def createTask(self, cmd):
        return Task(self, cmd)

    
    def showDeviceRack(self):
        if self.devRack is None:
            self.devRackDocks = {}
            self.devRack = QtGui.QMainWindow()
            for d in self.devices:
                dw = self.devices[d].deviceInterface()
                dock = QtGui.QDockWidget(d)
                dock.setFeatures(dock.AllDockWidgetFeatures)
                dock.setWidget(dw)
                
                self.devRackDocks[d] = dock
                self.devRack.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)
        self.devRack.show()
    
    def getCurrentDir(self):
        return self.dataManager.getCurrentDir()

    def setCurrentDir(self, newDir):
        return self.dataManager.setCurrentDir(newDir)

    def logMsg(self, msg, tags={}):
        cd = self.getCurrentDir()
        cd.logMsg(msg, tags)

    def quit(self):
        """Nicely request that all devices shut down"""
        if not self.alreadyQuit:
            for d in self.devices:
                print "Requesting %s quit.." % d
                self.devices[d].quit()
            self.alreadyQuit = True


class Task:
    def __init__(self, dm, command):
        self.dm = dm
        self.command = command
        self.result = None
        
        self.cfg = command['protocol']

        ## TODO:  set up data storage with cfg['storeData'] and ['writeLocation']
        
        self.devNames = command.keys()
        self.devNames.remove('protocol')
        self.devs = {}
        
        ## Create task objects. Each task object is a handle to the device which is unique for this protocol run.
        self.tasks = {}
        for devName in self.devNames:
            self.devs[devName] = self.dm.getDevice(devName)
            self.tasks[devName] = self.devs[devName].createTask(self.command[devName])
        
    def execute(self):
        ## Configure all subtasks. Some devices may need access to other tasks, so we make all available here.
        ## This is how we allow multiple devices to communicate and decide how to operate together.
        ## Each task may modify the startOrder array to suit its needs.
        self.startOrder = self.devs.keys()
        for devName in self.tasks:
            self.tasks[devName].configure(self.tasks, self.startOrder)
        
        ## Reserve all hardware before starting any
        for devName in self.tasks:
            self.tasks[devName].reserve()
        
        self.result = None
        
        ## Start tasks in specific order
        for devName in self.startOrder:
            self.tasks[devName].start()
            
        ## Wait until all tasks are done
        for t in self.tasks:
            while not self.tasks[t].isDone():
                time.sleep(10e-6)
        
        ## Stop all tasks
        for t in self.tasks:
            self.tasks[t].stop()
        
        ## Release all hardware for use elsewhere
        for t in self.tasks:
            self.tasks[t].release()
        
    def getResult(self):
        if self.result is None:
            ## Let each device generate its own output structure.
            result = {}
            for devName in self.tasks:
                result[devName] = self.tasks[devName].getResult()
            
            return result
        return self.result
