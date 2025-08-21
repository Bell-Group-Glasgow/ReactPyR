"""
So far, the OPC IR client is capable of:
- Obtaining background spectra
- Collecting real-time raw and processed spectra
- Setting and retrieving sampling intervals
- Starting, pausing, resuming, and stopping experiments.
"""

if __name__ == "__main__":

    import asyncio
    from ReactPyR_asyncua import ReactPyR

    # Example with all the above functionality.

    async def main():
        """The main event loop demonstrating basic function calls."""

        # Making the object.
        tcp_path = 'opc.tcp://localhost:62552/iCOpcUaServer'
        ir_machine = ReactPyR(opc_server_path=tcp_path)

        # Starting an experiment.
        template_name = 'DigitalDiscoveryProject'
        spectra_path = 'Digital Discovery Project\\asyncua_test10'
        await ir_machine.start_experiment(spectra_path, template_name, False)

        # Retrieving the intensities of previous background spectra.
        background = await ir_machine.get_last_background_spectra()

        # Collecting all the raw and processed IR spectra.
        await ir_machine.collect_raw_spectra()
        await asyncio.sleep(120)

        await ir_machine.collect_treated_spectra()

        # Changing sampling interval to 20 seconds.
        new_sampling_interval = 20
        await ir_machine.set_sampling_interval(new_sampling_interval)
        current_sampling_interval = await ir_machine.get_current_sampling_interval()
        if new_sampling_interval == current_sampling_interval:
            print('Sampling interval changed successfully.')

        # Pausing experiment for 20 seconds then resuming for another 20.
        await ir_machine.pause_experiment()
        await asyncio.sleep(20)
        await ir_machine.resume_experiment()
        await asyncio.sleep(20)

        # Stopping experiment
        await ir_machine.stop_experiment()

    asyncio.run(main())
