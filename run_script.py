import subprocess
import sys
import time

def run_modem_test():
    """Runs the modem test script (run_tests.py)"""
    print("Starting the modem test script...")
    # Run the modem test script (adjust the path to the script if needed)
    modem_process = subprocess.Popen([sys.executable, 'run_tests.py'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return modem_process

def run_odczyt_licznika():
    """Runs the odczyt_licznika.py script"""
    print("Starting the odczyt_licznika script...")
    # Run the TCP meter reading script (adjust the path to the script if needed)
    odczyt_process = subprocess.Popen([sys.executable, 'odczyt_licznika.py'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return odczyt_process

def main():
    # Start both processes
    modem_process = run_modem_test()
    odczyt_process = run_odczyt_licznika()

    try:
        # Wait for both processes to complete
        while True:
            # Check if either process has finished
            retcode_modem = modem_process.poll()
            retcode_odczyt = odczyt_process.poll()

            # If both processes have finished, break out of the loop
            if retcode_modem is not None and retcode_odczyt is not None:
                print("Both scripts have finished execution.")
                break

            # Optionally, add a small sleep to avoid CPU overload
            time.sleep(1)

    except KeyboardInterrupt:
        print("Process interrupted by user. Terminating both scripts...")
        modem_process.terminate()
        odczyt_process.terminate()

    finally:
        # Ensure both processes are cleaned up if necessary
        if modem_process.poll() is None:
            modem_process.terminate()
        if odczyt_process.poll() is None:
            odczyt_process.terminate()

        # Collect output and errors from both processes (optional)
        stdout_modem, stderr_modem = modem_process.communicate()
        stdout_odczyt, stderr_odczyt = odczyt_process.communicate()

        # Print the outputs and errors if you want to see the logs
        print("Modem test script output:\n", stdout_modem.decode())
        print("Modem test script errors:\n", stderr_modem.decode())
        print("Odczyt licznika script output:\n", stdout_odczyt.decode())
        print("Odczyt licznika script errors:\n", stderr_odczyt.decode())

if __name__ == "__main__":
    main()