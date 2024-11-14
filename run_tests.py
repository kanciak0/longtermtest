import logging
import threading
import time
from datetime import datetime, timedelta
from matplotlib import pyplot as plt
from Serial import SerialCommunicator  # Ensure this is correctly imported based on your project structure

def run_tests():
    """Runs the serial port logging process for testing the modem."""
    # Set up logging with a detailed format
    logging.basicConfig(filename='tests_log.txt', level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')

    # Initialize the SerialCommunicator with your config file and logs directory
    communicator = SerialCommunicator(config_file='config_file.txt', log_dir='logs')


    # Define a function to periodically call send_radio_change_command
    def periodic_radio_change():
        while True:
            time.sleep(9126)
            communicator.send_radio_change_command()
            communicator.monitor_radio_change()

    def periodic_module_change():
        while True:
            time.sleep(6521)
            communicator.send_module_change_command()
            communicator.monitor_module_change()

    def periodic_ping():
        while True:
            time.sleep(300)
            communicator.send_ping_command()
            communicator.monitor_ping_calls()

    logging.info("set radio_mode lte\n".encode())
    def update_uptime_percentage():
        while True:
            time.sleep(30)
            communicator.calculate_uptime_percentage()

    restart_thread = threading.Thread(target=communicator.monitor_modem_restart, daemon = True)
    restart_thread.start()

    uptime_thread = threading.Thread(target=update_uptime_percentage, daemon= True)
    uptime_thread.start()

    radio_thread = threading.Thread(target=periodic_radio_change, daemon=True)
    radio_thread.start()

    module_thread = threading.Thread(target=periodic_module_change, daemon=True)
    module_thread.start()

    ping_thread = threading.Thread(target=periodic_ping, daemon=True)
    ping_thread.start()

    try:
        while True:
            time.sleep(2746)
            communicator.plot_daily_module_change_test_results()
            communicator.plot_daily_radio_test_results()
            communicator.plot_daily_ping_test_results()
            communicator.plot_weekly_ping_test_results()
            communicator.plot_weekly_module_change_test_results()
            communicator.plot_weekly_radio_change_results()
            time.sleep(1)  # Delay to prevent CPU overuse

    except KeyboardInterrupt:
        # Log the user interrupt and gracefully stop all monitoring
        logging.info("Test logging interrupted by user.")

    finally:
        # Ensure that the communicator stops reading
        if communicator.ser:
            communicator.ser.close()  # Close the serial connection


if __name__ == "__main__":
    run_tests()
    plt.show()