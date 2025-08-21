"""The module focuses on controlling an IR machine via its OPC UA server."""

import asyncio
import os
from asyncio import Queue
from asyncua import Client, ua
import pandas as pd

class ReactPyR():
    """The icIR machine can only be controlled via its OPC UA server.
    Therefore, this class interfaces with the server to control the icIR machine."""

    def __init__(self, opc_server_path: str=None):

        # TCP path or OPC UA server.
        self.opc_server_path = opc_server_path

        # Queues for real time raw and treated spectra.
        # Items in queue are a list of intensities
        # Respective wavenumbers can be found in self.wave_numbers.
        self.raw_spectra_queue = Queue()
        self.treated_spectra_queue = Queue()

        self.last_background_spectra = None

        # Keeps track if a connection to the OPC UA server has been made.
        self.connected_client_bool = False

        # Keeps track if an experiment is running or not.
        self.experiment_running = False

        # Keeps track if an experiment is paused or not.
        self.experiment_paused = False

        # Time in seconds between IR sample collections.
        self.sampling_interval = None
        
        # # Loading the wavenumbers ic IR spits out (OPC server only gives a list of intensities).
        file_path = os.path.dirname(os.path.realpath(__file__))
        csv_path = os.path.join(file_path, 'wavelengths.csv')

        # # The standard wavenumber (cm^-1) axis usesd by ic IR.
        self.wave_numbers = pd.read_csv(csv_path)['Wavenumbercm-1'].tolist()

        # Node ids used to call methods and read variable values.
        self.methods_objects_node_id = 'ns=2;s=Local.iCIR.Probe1.Methods'
        self.start_experiment_node_id = 'ns=2;s=Local.iCIR.Probe1.Methods.Start Experiment'
        self.resume_experiment_node_id = 'ns=2;s=Local.iCIR.Probe1.Methods.Resume'
        self.pause_experiment_node_id = 'ns=2;s=Local.iCIR.Probe1.Methods.Pause'
        self.stop_experiment_node_id = 'ns=2;s=Local.iCIR.Probe1.Methods.Stop'
        self.set_sampling_interval_node_id = 'ns=2;s=Local.iCIR.Probe1.Methods.SetSamplingInterval'
        self.current_sampling_interval_node_id = 'ns=2;s=Local.iCIR.Probe1.CurrentSamplingInterval'
        self.lask_background_spectra_node_id = 'ns=2;s=Local.iCIR.Probe1.SpectraBackground'
        self.treated_spectra_node_id = 'ns=2;s=Local.iCIR.Probe1.SpectraTreated'
        self.raw_spectra_node_id = 'ns=2;s=Local.iCIR.Probe1.SpectraRaw'

        # Creating instance of OPC UA client.
        self.client = Client(url=self.opc_server_path)

    async def datachange_notification(self, node, val, data):
        """Function handles data inflow from the subscription event. 
        The name and parameters of this function SHOULD NOT be changed (see asyncua library)."""

        # Checking if its a raw spectra.
        if node.nodeid.to_string() == self.raw_spectra_node_id:
            await self.raw_spectra_queue.put(val)

        # Checking if its a treated spectra.
        if node.nodeid.to_string() == self.treated_spectra_node_id:
            self.treated_spectra_queue.put(val)

    async def get_last_background_spectra(self):
        """Gets the last collected background spectra from ic IR."""

        # Connecting to client if required.
        if not self.connected_client_bool:
            await self.client.connect()

        # Getting node value (spectra) from client.
        node = self.client.get_node(self.lask_background_spectra_node_id)
        self.last_background_spectra = await node.read_value()

        return self.last_background_spectra

    async def collect_treated_spectra(self):
        """Collecting real time treated IR spectra from OPC UA server via a client subscription."""

        # Connecting to client if required
        if not self.connected_client_bool:
            await self.client.connect()

        # Getting variable node
        myvar = self.client.get_node(self.treated_spectra_node_id)

        # subscribing to a variable node
        params = ua.CreateSubscriptionParameters(
            RequestedPublishingInterval=100,
            RequestedLifetimeCount=81000,
            RequestedMaxKeepAliveCount=27000
        )
        sub = await self.client.create_subscription(params, self)
        await sub.subscribe_data_change(myvar)

    async def collect_raw_spectra(self):
        """Collecting real time raw IR spectra from OPC UA server via a subscription."""

        # Connecting to client if required
        if not self.connected_client_bool:
            await self.connect()

        # Getting variable node
        myvar = self.client.get_node(self.raw_spectra_node_id)

        # subscribing to a variable node
        params = ua.CreateSubscriptionParameters(
            RequestedPublishingInterval=100,
            RequestedLifetimeCount=81000,
            RequestedMaxKeepAliveCount=27000
        )
        sub = await self.client.create_subscription(params, self)
        await sub.subscribe_data_change(myvar)

    async def call_method(self, parent_node_id, method_node_id, *method_inputs):
        """Calls the required method from server."""

        # Method needs to be called from methods object node.
        method_object_node = self.client.get_node(parent_node_id)
        method_node_id = self.client.get_node(method_node_id).nodeid

        # Calling method
        await method_object_node.call_method(method_node_id, *method_inputs)

    async def get_current_sampling_interval(self):
        """Returns current sampling interval (seconds) from OPC UA server."""

        # Connecting to client if required
        if not self.connected_client_bool:
            await self.client.connect()

        # Getting node value
        opc_value = await self.client.get_node(self.current_sampling_interval_node_id).read_value()
        return opc_value

    async def pause_experiment(self):
        """Pauses current icIR experiment with OPC UA server."""

        # Connecting to client if required
        if not self.connected_client_bool:
            await self.client.connect()

        if self.experiment_running:

            # Calling method from server
            await self.call_method(self.methods_objects_node_id, self.pause_experiment_node_id)
            self.experiment_paused = True

    async def stop_experiment(self):
        """Stops the current experiment (IR aquisition) with OPC UA server."""

        # Connecting to client if required
        if not self.connected_client_bool:
            await self.client.connect()

        if self.experiment_running:

            # Calling method from server
            await self.call_method(self.methods_objects_node_id, self.stop_experiment_node_id)

            await self.disconnect()

            self.experiment_running = False
            self.experiment_paused = False

    async def resume_experiment(self):
        """Resumes the current experiment with OPC UA server."""

        # Connecting to client if required
        if not self.connected_client_bool:
            await self.client.connect()

        if self.experiment_running and self.experiment_paused:

            # Calling method from server
            await self.call_method(self.methods_objects_node_id, self.resume_experiment_node_id)
            self.experiment_paused = False

    async def set_sampling_interval(self, sampling_interval:int):
        """Changes the spectra sampling interval (seconds) via OPC UA."""

        # Checking if sample interval is in an appropiate range (seconds).
        # Anything out of this range will result in a iCIR software error.
        if sampling_interval>3600 or sampling_interval<15:
            raise ValueError(f'Sampling_interval {sampling_interval} is not in range 15-3600 sec.')

        self.sampling_interval = sampling_interval

        # Connecting to client if required
        if not self.connected_client_bool:
            await self.client.connect()

        # Calling method from server
        await self.call_method(self.methods_objects_node_id,
                               self.set_sampling_interval_node_id,
                               sampling_interval)

    async def start_experiment(self, experiment_name:str,
                               template_name:str, collect_background=False):
        """Starts experiment (IR aquisition) on OPC UA server.
        experiment_name: the name of the experiment, accepts path like string.
        template_name: template name stored in 
        C:/ProgramData/METTLER TOLEDO/iC OPC UA Server/1.2/Templates
        ***icIR does not throw errors for wrong case use in naming. 
        It just fails to start the experiment.   
        """

        # Connecting to client if required
        if not self.connected_client_bool:
            await self.client.connect()

        if not self.experiment_running:

            # Calling method from server
            await self.call_method(self.methods_objects_node_id,
                                   self.start_experiment_node_id,
                                   experiment_name,
                                   template_name,
                                   collect_background)
            self.experiment_running = True

    async def connect(self):
        """Connects to opc server."""
        if not self.connected_client_bool:
            print('Connecting IR')
            await self.client.connect()
            self.connected_client_bool = True

    async def disconnect(self):
        """Disconnects from opc server."""
        if self.connected_client_bool:
            print('Disconnecting IR')
            await self.client.disconnect()
            self.connected_client_bool = False

    async def shutdown(self):
        """Shutting down IR machine involves disconnecting from server."""

        # Making sure the experiment running has been stopped.
        if self.experiment_running:
            await self.stop_experiment()

        else:
            await self.disconnect()
