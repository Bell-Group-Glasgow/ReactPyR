from opcua import Client
from threading import Thread
import pandas as pd
import os
import time
from queue import Queue 
import pickle
import matplotlib.pylab as plt
import numpy as np

class ReactPyR():
    """The icIR machine can only be controlled via its OPC UA server. This class interfaces with the server to control the icIR machine."""
    
    def __init__(self, opc_server_path: str=None):        
        self.opc_server_path = opc_server_path          # TCP path or OPC UA server
        self.raw_spectra_queue = Queue()                # Queue for the collected real time raw spectra
        self.treated_spectra_queue = Queue()            # Queue for the collected real time treated spectra
        self.last_background_spectra = None             # Saves the last background taken by OPC UA.
        self.connected_client_bool = False              # Keeps track if a connection to the OPC UA server has been made.
        self.experiment_running = False                 # Keeps track if an experiment is running or not.

        # Loading the wavenumbers ic IR spits out (OPC server only gives a list of intensities).
        file_path = os.path.dirname(os.path.realpath(__file__))
        csv_path = os.path.join(file_path, 'wavelengths.csv')
        self.wave_numbers = pd.read_csv(csv_path)['Wavenumbercm-1'].tolist() # The standard wavenumber (cm^-1) axis usesd by ic IR.

        # NodeIds and browse names of relevant nodes in OPC UA Client
        self.methods_object_id = 'ns=2;s=Local.iCIR.Probe1.Methods'                  
        self.raw_spectra_node_id = 'ns=2;s=Local.iCIR.Probe1.SpectraRaw'
        self.treated_spectra_node_id = 'ns=2;s=Local.iCIR.Probe1.SpectraTreated'
        self.lask_background_spectra_node_id = 'ns=2;s=Local.iCIR.Probe1.SpectraBackground'
        self.current_sampling_interval_node_id = 'ns=2;s=Local.iCIR.Probe1.CurrentSamplingInterval'
        self.pause_node_id = 'ns=2;s=Local.iCIR.Probe1.Methods.Pause'
        self.stop_node_id = 'ns=2;s=Local.iCIR.Probe1.Methods.Stop'
        self.resume_node_id = 'ns=2;s=Local.iCIR.Probe1.Methods.Resume'
        self.set_sampling_interval_node_id = 'ns=2;s=Local.iCIR.Probe1.Methods.SetSamplingInterval'
        self.start_experiment_node_id = 'ns=2;s=Local.iCIR.Probe1.Methods.Start Experiment'

        # Creating instance of OPC UA client
        self.client = Client(self.opc_server_path)

    def datachange_notification(self, node, val, data):
        """Function handles data inflow from the subscription event to OPC server. The name of this function can not be changed."""

        nodeId = node.nodeid.to_string()

        # Checking if its a raw spectra
        if nodeId == self.raw_spectra_node_id:
            self.raw_spectra_queue.put(val)

        # Checking if its a treated spectra
        if nodeId == self.treated_spectra_node_id:
            self.treated_spectra_queue.put(val)

    def get_last_background_spectra(self):
        """Gets the last collected background spectra from ic IR."""
        
        # Connecting to client if required
        if not self.connected_client_bool:
            self.connect()

        # Connecting to client and getting node value
        self.last_background_spectra = self.client.get_node(self.lask_background_spectra_node_id).get_value()
        
        return self.last_background_spectra

    def collect_treated_spectra(self):
        """Collecting treated IR specctra from OPC UA server. This creates a subscription to the treated spectra node."""

        # Connecting to client if required
        if not self.connected_client_bool:
            self.connect()

        spectra = self.client.get_node(self.treated_spectra_node_id)
        subscription = self.client.create_subscription(200, handler=self)
        subscription.subscribe_data_change(spectra)
        subscription.subscribe_events()

    def collect_raw_spectra(self):
        """Collecting raw IR spectra from OPC UA server. This creates a subscription to the raw spectra node."""

        # Connecting to client if required
        if not self.connected_client_bool:
            self.connect()

        spectra = self.client.get_node(self.raw_spectra_node_id)
        subscription = self.client.create_subscription(200, handler=self)
        subscription.subscribe_data_change(spectra)
        subscription.subscribe_events()
    
    def get_current_sampling_interval(self):
        """Returns current sampling interval from OPC UA server."""

        # Connecting to client if required
        if not self.connected_client_bool:
            self.connect()

        # Getting node value
        opc_value = self.client.get_node(self.current_sampling_interval_node_id).get_value()
        return opc_value
    
    def pause_experiment(self):
        """Pauses current icIR experiment with OPC UA server."""

        # Connecting to client if required
        if not self.connected_client_bool:
            self.connect()
            
        # Method must be called from methods object node
        methods_object_node = self.client.get_node(self.methods_object_id)
        
        # The method to be called
        method = self.client.get_node(self.pause_node_id)
        methods_object_node.call_method(method)        

    def stop_experiment(self):
        """Stops the current experiment with OPC UA server."""

        # Connecting to client if required
        if not self.connected_client_bool:
            self.connect()
        
        # Method must be called from methods object node
        methods_object_node = self.client.get_node(self.methods_object_id)
        
        # The method to be called
        method = self.client.get_node(self.stop_node_id)
        methods_object_node.call_method(method)

        self.disconnect()
        
        self.experiment_running = False

    def resume_experiment(self):
        """Resumes the current experiment with OPC UA server."""

        # Connecting to client if required
        if not self.connected_client_bool:
            self.connect()

        # Method must be called from methods object node
        methods_object_node = self.client.get_node(self.methods_object_id)
        
        # The method to be called
        method = self.client.get_node(self.resume_node_id)
        methods_object_node.call_method(method)

    def set_sampling_interval(self, sampling_interval:int):
        """Changes the spectra sampling interval via OPC UA."""

        # Checking if sample interval is not smaller than 15 sec and not larger than 3600 sec (1 hour)
        if sampling_interval>3600 or sampling_interval<15:
            raise ValueError(f'Sampling_interval {sampling_interval} is not in range 15-3600 sec.')
        
        self.sampling_interval = sampling_interval
 
        # Connecting to client if required
        if not self.connected_client_bool:
            self.connect()

        # Method must be called from methods object node
        methods_object_node = self.client.get_node(self.methods_object_id)
        
        # The method to be called
        method = self.client.get_node(self.set_sampling_interval_node_id)
        methods_object_node.call_method(method, sampling_interval)

    def start_experiment(self, experiment_name:str, template_name:str, collect_background=False):
        """Starts experiment on OPC UA server.
        experiment_name: the name of the experiment, accepts path like string.
        template_name: name of template to use stored in C:\ProgramData\METTLER TOLEDO\iC OPC UA Server\1.2\Templates """

        # Connecting to client if required
        if not self.connected_client_bool:
            self.connect()

    
        # Method must be called from methods object node
        methods_object_node = self.client.get_node(self.methods_object_id)
        method = self.client.get_node(self.start_experiment_node_id)
        methods_object_node.call_method(method, experiment_name, template_name, collect_background)
        self.experiment_running = True

    def connect(self):
        """Connects to opc server."""
        if not self.connected_client_bool:
            print('Connecting IR')
            
            self.client.connect()

            self.connected_client_bool = True

    def disconnect(self):
        """Disconnects from opc server"""
        if self.connected_client_bool:
            print('Disconnecting IR')
            self.client.disconnect()
            self.connected_client_bool = False

    def shutdown(self):
        """Shutting down IR machine involves disconnecting from server"""

        # Making sure the experiment running has been stopped.
        if self.experiment_running:
            self.stop_experiment()

        else:
            self.disconnect()

if __name__ == "__main__":

    #Example use
    tcp_path = 'opc.tcp://localhost:62552/iCOpcUaServer'
    ReactPyR1 = ReactPyR(opc_server_path=tcp_path)
    
    spectra_path = 'Digital Discovery Project\\test1'
    template_name = 'DigitalDiscoveryProject'
    ReactPyR1.start_experiment(spectra_path, template_name)
    time.sleep(15)
    ReactPyR1.stop_experiment()

    ReactPyR1.shutdown()
