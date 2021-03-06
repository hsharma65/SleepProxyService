#!/usr/bin/env python
# encoding: utf-8
"""
CCd.py

This is the Clean Clusters daemon. This listens for activity on the node. If it
detects low activity on the node, it publishes a request to sleep. The masters 
nodes in the cluster (running the sleep proxy plugin) will respond with an 
acknowledgement. The node will then go to sleep.
"""
import SocketServer
import sys
import os
import common
import subprocess
import threading
import select
import random
import time

LAST_JOB_FINISH             = time.time()
CURRENTLY_PROCESSING_JOB    = False
JOB_CHECK_SLEEP_INTVL       = 60    # 1 minute
# IDLE_BEFORE_SLEEP_INTVL     = 240   # 4 minutes
SLEEP_REQ_ACCEPT_WAIT_INTVL = 240   # 4 minutes
monitor                     = CCMonitor()

class CCd(SocketServer.StreamRequestHandler):
    def handle(self):
        data = self.rfile.readline().strip()
        if data == "SLEEP":
            self.sleep()
        else:
            logging.error("CCd received malformed data! Check this!")

        
class ProcStdinFeeder (threading.Thread):
    """This class is responsible for receiving data from the network and 
    pipeing it into the process's  stdin"""
    
    def __init__(self, proc, sock):
        self.proc = proc
        self.sock = sock
        threading.Thread.__init__ ( self )
        
    def run(self):
        while True:
            try:
                read_byte = self.sock.read(1)
                self.proc.stdin.write(read_byte)
            except: # exception is raised when network socket is closed and process is dead
                break

class CCexecd(SocketServer.StreamRequestHandler):
    """This class receives the command to be executed along with stdin input 
    and pipes back stdout over the network"""
    
        
    
    def handle(self):
        CURRENTLY_PROCESSING_JOB = True
        try:
            command = self.rfile.readline().strip()
            proc = subprocess.Popen(command.split(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)
            ProcStdinFeeder(proc, self.rfile).start()
            while True:
                output = proc.stdout.read(100)
                if output == "":
                    break
                self.wfile.write(output)
            self.wfile.flush()
        except:
            logging.exception("Could not complete execution of job")
            self.wfile.write("ERROR")
            self.wfile.flush()
        finally:
            CURRENTLY_PROCESSING_JOB = False
            LAST_JOB_FINISH = time.time()   # also log failed job, it was an attempt after all
    
class CCMonitor(object):
    """This class monitor's the system for any jobs currently being run and issues a request to sleep when idle"""
    
    def __init__(self):
        self.last_sleep_metric = False
        
    def start(self):
        while True:
            if self.check_if_idle():
                request_sleep()
            else:
                identify_no_sleep()            
            time.sleep(JOB_CHECK_SLEEP_INTVL)  
            
    def check_if_idle(self):
        if not CURRENTLY_PROCESSING_JOB and time.time() - LAST_JOB_FINISH > IDLE_BEFORE_SLEEP_INTVL:
            return True
        return False  
    
    def request_sleep(self):
        """Inform gmond that this node wants to go to sleep"""
        subprocess.Popen("gmetric -n \"SLEEP_INTENT\" -v \"YES\" -t \"string\"")
        self.last_sleep_metric = True
    
    def identify_no_sleep(self):
        """Inform gmond that this node does not need to go to sleep"""
        if self.last_sleep_metric:
            return
        subprocess.Popen("gmetric -n \"SLEEP_INTENT\" -v \"NO\" -t \"string\"")
        self.last_sleep_metric = False
        
    def sleep(self):
        try:
            power_state = open('/sys/power/state', 'w')
            if self.check_if_idle():
                logging.debug("Node no longer idle")
                power_state.close()
                return
            # power_state.write('mem')
            power_state.close()
        except:
            logging.exception("Could not go to sleep!")
    
def main():
    common.ServiceLauncher(common.CCD_PORT, CCd).start()
    common.ServiceLauncher(common.CCD_EXEC_PORT, CCexecd).start()
    monitor.start()
#    CCdStarter().start()
#    CCexecdStarter().start()


if __name__ == '__main__':
    main()

