import configparser
import logging
import platform
import re
import threading
import time

import serial
import os
from datetime import datetime, timedelta

from matplotlib import pyplot as plt

#TODO: GIGA HACKS IMPLEMENTED, REFACTOR AS FAST AS POSSIBLE, WHEN 1ST VERSION WORKS
class SerialCommunicator:
    def __init__(self, config_file: str = 'config_file.txt', log_dir: str = 'logs') -> None:
        self.start_day = datetime.now()
        self.config_file = config_file
        config = configparser.ConfigParser()
        config.read(config_file)

        system = platform.system()
        if system == "Windows":
            config_section = 'serialWindows'
        elif system == "Linux":
            config_section = 'serialLinux'
        else:
            raise OSError(f"Unsupported platform: {system}")

        if not config.has_section(config_section):
            raise configparser.NoSectionError(config_section)
        self.password = config.get(config_section,'password')
        self.port = config.get(config_section, 'port')
        self.baudrate = config.getint(config_section, 'baudrate')
        self.timeout = config.getfloat(config_section, 'timeout')

        self.log_dir = log_dir
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        sanitized_port = self.port.replace("/", "_").replace(":", "_")
        self.log_file = os.path.join(self.log_dir, f'serial_log_{sanitized_port}.txt')

        self.lock = threading.Lock()
        self.ser = None
        self._connect_serial()
        self.start_date = datetime.now().date()
        # Uptime tracking
        self.total_uptime = timedelta(0)
        self.program_start_time = datetime.now()
        self.last_restart_time = None
        self.is_modem_up = True
        self.uptime_start_time = datetime.now()
        self.last_change_time = time.time()  # Track the last change time
        self.module_change_interval =  300  # Change interval in seconds (3 hours)
        self.radio_change_interval = 60 # Change interval in seconds (3 hours)
        self.ping_interval = 5 * 60

        self.restart_counter = 0
        # Test tracking
        self.total_apn_tests = 0
        self.total_radio_tests = 0
        self.total_module_tests = 0
        self.total_ping_tests = 0

        # Successful/failed test tracking
        self.succesful_ping_tests = 0
        self.failed_ping_tests = 0
        self.succesful_apn_login_test = 0
        self.failed_apn_login_test = 0
        self.succesful_radio_change_test = 0
        self.failed_radio_change_test = 0
        self.succesful_module_change_test = 0
        self.failed_module_change_test = 0

        # Daily tracking arrays
        self.daily_failed_radio_change_test = [0] * 7
        self.daily_successful_radio_change_test = [0] * 7


        self.daily_failed_module_change_test = [0] * 7
        self.daily_successful_module_change_test = [0] * 7

        self.daily_successful_apn_login_tests = [0] * 7
        self.daily_failed_apn_login_tests = [0] * 7

        self.daily_successful_ping_tests = [0] * 7
        self.daily_failed_ping_tests = [0] * 7
        # Time of last test for hourly update
        self.last_test_hour = datetime.now().hour

    def _connect_serial(self):
        """Attempts to connect to the serial port."""
        try:
            self.ser = serial.Serial(self.port, baudrate=self.baudrate, timeout=self.timeout)
            logging.info(f"Connected to {self.port}")
        except serial.SerialException as e:
            logging.error(f"Failed to connect to {self.port}: {e}")
            self.ser = None

    def wait_for_message(self, expected_message: str, timeout: int = 45) -> bool:
        start_time = time.time()
        buffer = ""
        unknown_command_pattern = re.compile(r"nieznane polecenie '([^']+)'")

        while True:
            if time.time() - start_time > timeout:
                return False

            if self.ser.in_waiting > 0:
                data = self.read()
                buffer += data

                match = unknown_command_pattern.search(buffer)
                if match:
                    command = match.group(1)
                    message = f"Skipping test due to unknown command: 'nieznane polecenie {command}'"
                    logging.warning(message)

                # Check if the expected message is found
                if expected_message in buffer:
                    return True

    def wait_for_message_and_take_value(self, expected_message: str, timeout: int = 30) -> str:
        start_time = time.time()
        buffer = ""

        while time.time() - start_time < timeout:
            if self.ser.in_waiting > 0:
                data = self.ser.read(self.ser.in_waiting).decode()  # Read all available data
                buffer += data

                if expected_message in buffer:
                    return buffer

            time.sleep(0.1)  # Small delay to allow data to accumulate

        return ""  # Return an empty string if message not found within timeout

    def is_debug_mode(self) -> bool:
        self.ser.write(b'\n\r')
        if not self.wait_for_message("debug >", 3):
            return False
        else:
            return True

    def login_admin(self) -> bool:
        if self.is_debug_mode():
            return False
        self.ser.write('login\n'.encode())
        self.ser.write(f'{self.password}\r\n'.encode())

        if self.wait_for_message("LCT: OK logged in"):
            print("Login: OK")
            return True
        else:
            print("Login: ERROR")
            return False

    @staticmethod
    def _is_unwanted_entry(entry: str) -> bool:
        return entry == "" or entry.startswith("debug >")

    def read(self) -> str:
        try:
            if self.ser and self.ser.in_waiting > 0:
                data = self.ser.read(self.ser.in_waiting or 1).decode('utf-8')
                self._log_data(data)
                return data
        except serial.SerialException as e:
            logging.error(f"Disconnected from {self.port}: {e}")
            logging.info(f"Attempting to reconnect to {self.port}...")
            self.ser = None
        return ""

    def _log_data(self, data: str) -> None:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        log_entries = data.splitlines()
        with open(self.log_file, 'a') as f:
            for entry in log_entries:
                entry = entry.strip()
                if entry and not self._is_unwanted_entry(entry):
                    f.write(f"{timestamp} - {entry}\n")

    def calculate_uptime_percentage(self):
        """Calculates the uptime percentage and logs it every 5 minutes."""
        # Calculate the total time the program has been running
        total_time = datetime.now() - self.program_start_time

        # If the modem is still up, accumulate uptime since the last start
        if self.is_modem_up and self.uptime_start_time:
            self.total_uptime += datetime.now() - self.uptime_start_time
            self.uptime_start_time = datetime.now()  # Reset uptime start time for the next interval

        # Calculate uptime percentage, preventing division by zero
        uptime_percentage = (self.total_uptime / total_time) * 100 if total_time.total_seconds() > 0 else 0

        logging.info(f"Uptime percentage: {uptime_percentage:.2f}%")

        # Log the uptime percentage to a file with timestamp
        with open(self.log_file, 'a') as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} - Uptime percentage: "
                    f"{uptime_percentage:.2f}%\n")

    def monitor_modem_restart(self) -> None:
        """Monitors the serial port continuously for modem restart messages and tracks uptime and restarts."""
        buffer = ""

        while True:
            if self.ser is None:
                self._connect_serial()

            if self.ser and self.ser.in_waiting > 0:
                data = self.read()
                buffer += data

                if re.search(r" Restart w ciagu 3 s", buffer):
                    self.restart_counter += 1  # Increment restart counter
                    logging.info(f"Modem restarts: {self.restart_counter}")
                    buffer = ""
                    if self.is_modem_up and self.uptime_start_time:
                        downtime_start = datetime.now()
                        self.total_uptime += downtime_start - self.uptime_start_time  # Track downtime
                    self.is_modem_up = False
                    self.last_restart_time = datetime.now()
                    self.uptime_start_time = None

                if re.search(r"Modul radiowy poprawnie wykryty i zainicjowany", buffer):
                    logging.info("Modem has successfully restarted.")
                    self.is_modem_up = True
                    self.uptime_start_time = datetime.now()
                    buffer = ""

            time.sleep(1)

    def monitor_ping_calls(self) -> None:
        """Monitors for a ping response with a 30-second timeout."""
        buffer = ""
        end_time = datetime.now() + timedelta(seconds=30)  # 30-second timeout
        ping_successful = False  # Flag to track if ping was successful

        while datetime.now() < end_time:
            if self.ser and self.ser.in_waiting > 0:
                data = self.ser.read(self.ser.in_waiting).decode('utf-8', errors='ignore')
                buffer += data
                logging.debug(f"Buffer updated: {buffer}")

                if "recv from 8.8.8.8:" in buffer:
                    logging.info("Ping test successful.")
                    self._increment_ping_test_count(success=True)
                    ping_successful = True  # Mark as successful
                    break  # Exit loop after success

            time.sleep(0.1)

        # Only increment as failed if no success was recorded
        if not ping_successful:
            logging.info("Ping test failed (timeout).")
            self._increment_ping_test_count(success=False)

    def _increment_ping_test_count(self, success: bool) -> None:
        """Increments the daily test count, accounting for day transitions."""
        current_day = (datetime.now().date() - self.start_date).days % 7  # Rolling 7-day index
        if success:
            self.daily_successful_ping_tests[current_day] += 1
            self.succesful_ping_tests += 1
        else:
            self.daily_failed_ping_tests[current_day] += 1
            self.failed_ping_tests += 1

    def _increment_module_test_count(self, success: bool) -> None:
        """Increments the daily test count, accounting for day transitions."""
        current_day = (datetime.now().date() - self.start_date).days % 7  # Rolling 7-day index
        if success:
            self.daily_successful_module_change_test[current_day] += 1
            self.succesful_module_change_test += 1
        else:
            self.daily_failed_module_change_test[current_day] += 1
            self.failed_module_change_test += 1

    def _increment_radio_test_count(self, success: bool) -> None:
        """Increments the daily test count, accounting for day transitions."""
        current_day = (datetime.now().date() - self.start_date).days % 7  # Rolling 7-day index
        if success:
            self.daily_successful_radio_change_test[current_day] += 1
            self.succesful_radio_change_test += 1
        else:
            self.daily_failed_radio_change_test[current_day] += 1
            self.failed_radio_change_test +=1

    def monitor_module_change(self) -> None:
        retry_count = 0
        max_retries = 2
        while retry_count <= max_retries:
            time.sleep(3)
            buffer = ""
            end_time = datetime.now() + timedelta(seconds=40)
            module_change_successful = False  # Flag to track if module change was successful

            while datetime.now() < end_time:
                if self.ser and self.ser.in_waiting > 0:
                    data = self.ser.read(self.ser.in_waiting).decode('utf-8', errors='ignore')
                    buffer += data
                    logging.debug(f"Buffer updated: {buffer}")

                    # Check for module change success in the buffer
                    if "N27" in buffer or "N717" in buffer:
                        logging.info("Module change successful.")
                        module_change_successful = True  # Mark as successful
                        self._increment_module_test_count(success=True)
                        self.restart_counter -= 1
                        break  # Exit the loop if success message is found

                time.sleep(1)  # Sleep to prevent high CPU usage

            if module_change_successful:
                break  # Exit the retry loop if the module change is successful
            else:
                retry_count += 1  # Increment the retry count
                self.restart_counter -= 1
                # If we have reached the max retries, stop and log failure
                if retry_count > max_retries:
                    logging.error("Module change failed after 2 retries.")
                    self._increment_module_test_count(success=False)
                    break  # Exit the loop after max retries

                # Retry sending the module change command
                self.send_module_change_command()

    def monitor_radio_change(self) -> None:
        retry_count = 0
        max_retries = 2
        while retry_count <= max_retries:
            time.sleep(3)
            buffer = ""
            end_time = datetime.now() + timedelta(seconds=40)
            radio_change_successful = False  # Flag to track if radio change was successful

            while datetime.now() < end_time:
                if self.ser and self.ser.in_waiting > 0:
                    data = self.ser.read(self.ser.in_waiting).decode('utf-8', errors='ignore')
                    buffer += data
                    logging.debug(f"Buffer updated: {buffer}")

                    # Check for radio change success in the buffer
                    if "RAT: LTE" in buffer or "RAT: EDGE" in buffer:
                        logging.info("Radio change successful.")
                        self._increment_radio_test_count(success=True)
                        self.restart_counter -= 1
                        radio_change_successful = True  # Mark as successful
                        break  # Exit the loop if success message is found

                time.sleep(1)  # Sleep to prevent high CPU usage

            if radio_change_successful:
                break  # Exit the retry loop if the radio change is successful
            else:
                retry_count += 1  # Increment the retry count
                self.restart_counter -= 1

                # If we have reached the max retries, stop and log failure
                if retry_count > max_retries:
                    logging.error("Radio change failed after 2 retries.")
                    self._increment_radio_test_count(success=False)
                    break  # Exit the loop after max retries

                self.send_radio_change_command()

    def plot_daily_radio_test_results(self) -> None:
        """Plots the test results as a pie chart."""

        total_positive =  self.succesful_radio_change_test
        total_negative =  self.failed_radio_change_test

        labels = []
        sizes = []
        colors = []

        if total_positive > 0:
            labels.append('Successful Tests')
            sizes.append(total_positive)
            colors.append('green')
        if total_negative > 0:
            labels.append('Failed Tests')
            sizes.append(total_negative)
            colors.append('red')

        if not sizes:
            sizes = [1]
            labels = ['No Tests']
            colors = ['grey']

        date_str = datetime.now().strftime('%Y-%m-%d')

        # Custom function to format labels
        def func(pct, allvals):
            absolute = int(round(pct / 100. * sum(allvals)))
            return f'{absolute} ({pct:.1f}%)'

        # Plotting
        plt.figure(figsize=(8, 8))
        wedges, texts, autotexts = plt.pie(sizes, labels=labels, autopct=lambda pct: func(pct, sizes),
                                           colors=colors, shadow=False, startangle=90)
        plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle
        plt.title(f'Radio Test Results - {date_str}')

        # Improve label visibility
        for text in autotexts:
            text.set_color('white')
            text.set_fontsize(12)

        timestamp = datetime.now().strftime('%Y-%m-%d')  # Format for the filename
        plt.savefig(os.path.join(self.log_dir, f'radio_change_test_results_{timestamp}.png'))
        plt.close()

    def plot_daily_ping_test_results(self) -> None:
        """Plots the test results as a pie chart."""

        total_positive = self.succesful_ping_tests
        total_negative = self.failed_ping_tests

        labels = []
        sizes = []
        colors = []

        if total_positive > 0:
            labels.append('Successful Tests')
            sizes.append(total_positive)
            colors.append('green')
        if total_negative > 0:
            labels.append('Failed Tests')
            sizes.append(total_negative)
            colors.append('red')

        if not sizes:
            sizes = [1]
            labels = ['No Tests']
            colors = ['grey']

        date_str = datetime.now().strftime('%Y-%m-%d')

        # Custom function to format labels
        def func(pct, allvals):
            absolute = int(round(pct / 100. * sum(allvals)))
            return f'{absolute} ({pct:.1f}%)'

        # Plotting
        plt.figure(figsize=(8, 8))
        wedges, texts, autotexts = plt.pie(sizes, labels=labels, autopct=lambda pct: func(pct, sizes),
                                           colors=colors, shadow=False, startangle=90)
        plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle
        plt.title(f'Ping Test Results - {date_str}')

        # Improve label visibility
        for text in autotexts:
            text.set_color('white')
            text.set_fontsize(12)

        timestamp = datetime.now().strftime('%Y-%m-%d')  # Format for the filename
        plt.savefig(os.path.join(self.log_dir, f'ping_test_results_{timestamp}.png'))
        plt.close()  # Close the figure to free up memory

    def plot_daily_module_change_test_results(self) -> None:
        """Plots the test results as a pie chart."""

        total_positive = self.succesful_module_change_test
        total_negative = self.failed_module_change_test

        labels = []
        sizes = []
        colors = []

        if total_positive > 0:
            labels.append('Successful Tests')
            sizes.append(total_positive)
            colors.append('green')
        if total_negative > 0:
            labels.append('Failed Tests')
            sizes.append(total_negative)
            colors.append('red')

        if not sizes:
            sizes = [1]
            labels = ['No Tests']
            colors = ['grey']

        date_str = datetime.now().strftime('%Y-%m-%d')

        # Custom function to format labels
        def func(pct, allvals):
            absolute = int(round(pct / 100. * sum(allvals)))
            return f'{absolute} ({pct:.1f}%)'

        # Plotting
        plt.figure(figsize=(8, 8))
        wedges, texts, autotexts = plt.pie(sizes, labels=labels, autopct=lambda pct: func(pct, sizes),
                                           colors=colors, shadow=False, startangle=90)
        plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle
        plt.title(f'Module Test Results - {date_str}')

        # Improve label visibility
        for text in autotexts:
            text.set_color('white')
            text.set_fontsize(12)

        timestamp = datetime.now().strftime('%Y-%m-%d')  # Format for the filename
        plt.savefig(os.path.join(self.log_dir, f'module_change_test_results_{timestamp}.png'))
        plt.close()  # Close the figure to free up memory

    def plot_weekly_module_change_test_results(self) -> None:
        dates = [(datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
        successful_tests = self.daily_successful_module_change_test
        failed_tests = self.daily_failed_module_change_test

        bar_width = 0.35  # Width of the bars
        index = range(len(dates))  # Create an index for the x-axis

        # Create a bar chart
        plt.figure(figsize=(10, 6))
        bars_successful = plt.bar(index, successful_tests, width=bar_width, label="Successful Tests", color="green",
                                  align='center')
        bars_failed = plt.bar([i + bar_width for i in index], failed_tests, width=bar_width, label="Failed Tests",
                              color="red",
                              align='center')
        for bar in bars_successful:
            plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() - 0.3, str(bar.get_height()), ha='center',
                     va='bottom')
        for bar in bars_failed:
            plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() - 0.3, str(bar.get_height()), ha='center',
                     va='bottom')
        # Labeling the axes and title
        plt.xlabel("Date")
        plt.ylim(0,15)
        plt.ylabel("Number of Tests")
        plt.title("Upcoming Daily Test Results for the Next Week")
        plt.xticks([i + bar_width / 2 for i in index], dates)  # Center the x-ticks between the bars
        plt.legend()
        plt.grid(axis='y')
        plt.tight_layout()
        plt.savefig(os.path.join(self.log_dir, f'weekly_module_change_test_results.png'))

    def plot_weekly_ping_test_results(self) -> None:
        dates = [(datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
        successful_tests = self.daily_successful_ping_tests
        failed_tests = self.daily_failed_ping_tests

        bar_width = 0.35
        index = range(len(dates))

        plt.figure(figsize=(10, 6))
        bars_successful = plt.bar(index, successful_tests, width=bar_width, label="Successful Tests", color="green",
                                  align='center')
        bars_failed = plt.bar([i + bar_width for i in index], failed_tests, width=bar_width, label="Failed Tests",
                              color="red", align='center')

        plt.ylim(0, 10)  # Adjust the y-limit to better fit your data

        for bar in bars_successful:
            plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() - 0.3, str(bar.get_height()), ha='center',
                     va='bottom')
        for bar in bars_failed:
            plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() - 0.3, str(bar.get_height()), ha='center',
                     va='bottom')

        plt.xlabel("Date")
        plt.ylabel("Number of Tests")
        plt.title("Upcoming Daily Test Results for the Next Week")
        plt.xticks([i + bar_width / 2 for i in index], dates)
        plt.legend()
        plt.grid(axis='y')
        plt.tight_layout()
        plt.savefig(os.path.join(self.log_dir, f'weekly_ping_test_results.png'))
        plt.close()

    def plot_weekly_radio_change_results(self) -> None:
        dates = [(datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
        successful_tests = self.daily_successful_radio_change_test
        failed_tests = self.daily_failed_radio_change_test

        bar_width = 0.35  # Width of the bars
        index = range(len(dates))  # Create an index for the x-axis

        # Create a bar chart
        plt.figure(figsize=(10, 6))
        bars_successful = plt.bar(index, successful_tests, width=bar_width, label="Successful Tests", color="green",
                                  align='center')
        bars_failed = plt.bar([i + bar_width for i in index], failed_tests, width=bar_width, label="Failed Tests",
                              color="red",
                              align='center')
        for bar in bars_successful:
            plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() - 0.3, str(bar.get_height()), ha='center',
                     va='bottom')
        for bar in bars_failed:
            plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() - 0.3, str(bar.get_height()), ha='center',
                     va='bottom')

        # Labeling the axes and title
        plt.xlabel("Date")
        plt.ylim(0,15)
        plt.ylabel("Number of Tests")
        plt.title("Upcoming Daily Test Results for the Next Week")
        plt.xticks([i + bar_width / 2 for i in index], dates)  # Center the x-ticks between the bars
        plt.legend()
        plt.grid(axis='y')

        plt.tight_layout()
        plt.savefig(os.path.join(self.log_dir, f'weekly_radio_change_test_results.png'))

    def send_ping_command(self) -> None:
        """Sends the 'ip.ping 8.8.8.8' command to the modem and signals response monitoring."""
        if self.ser is not None:
            try:
                time.sleep(1)
                self.login_admin()
                logging.info("Sending command: ip.ping 8.8.8.8")
                self.ser.write("ip.ping 8.8.8.8\n".encode('utf-8'))
                self.total_ping_tests += 1
            except serial.SerialException as e:
                    logging.error(f"Error sending command to {self.port}: {e}")

    def send_module_change_command(self) -> None:
        if self.ser is not None:
            try:
                time.sleep(2)
                self.login_admin()
                logging.info("Checking module")
                self.ser.write("print active_radio\n".encode())
                response = self.wait_for_message_and_take_value("active_radio=")
                logging.debug(f"Received response: {response}")
                active_radio = self.extract_active_radio(response)
                if active_radio =="2":
                    self.ser.write("set active_radio 1\n".encode())
                elif active_radio == "1":
                    self.ser.write("set active_radio 2\n".encode())
                self.ser.write("save\n".encode())
                self.ser.write("reset\n".encode())
                self.total_module_tests += 1
            except serial.SerialException as e:
                logging.error(f"Error sending command to {self.port}: {e}")

    def send_radio_change_command(self) -> None:
        if self.ser is not None:
            try:
                time.sleep(2)
                self.login_admin()
                logging.info("Checking radio")
                time.sleep(0.5)
                self.ser.write("print radio_mode\n".encode())

                # Wait for a response that contains "radio_mode="
                response = self.wait_for_message_and_take_value("radio_mode=")
                logging.debug(f"Received response: {response}")

                # Extract the specific radio mode value
                radio_mode = self.extract_radio_mode(response)

                # Check radio mode and send corresponding command
                if radio_mode == "lte":
                    self.ser.write("set radio_mode 2g\n".encode())
                    logging.info("set radio_mode lte\n".encode())
                elif radio_mode == "2g":
                    self.ser.write("set radio_mode lte\n".encode())
                    logging.info("set radio_mode 2g\n".encode())
                elif radio_mode == "auto":
                    self.ser.write("set radio_mode lte \n".encode())
                    logging.info("set radio_mode lte\n".encode())
                else:
                    logging.warning(f"Unexpected radio mode: {radio_mode}")
                self.ser.write("save\n".encode())
                self.ser.write("reset\n".encode())
                # Update counters and last change time
                self.total_radio_tests += 1
            except serial.SerialException as e:
                logging.error(f"Error sending command to {self.port}: {e}")


    def start_monitors(self):
        """Starts monitoring functions sequentially without threading."""
        self.monitor_modem_restart()
        self.monitor_ping_calls()
        self.monitor_module_change()
        self.monitor_radio_change()

    @staticmethod
    def extract_active_radio(response):
        for line in response.splitlines():
            if "active_radio=" in line:
                # Extracts the mode after 'radio_mode=' and removes any extra whitespace
                return line.split("active_radio=")[-1].strip()
        return ""

    @staticmethod
    def extract_radio_mode(response: str) -> str:
        for line in response.splitlines():
            if "radio_mode=" in line:
                # Extracts the mode after 'radio_mode=' and removes any extra whitespace
                return line.split("radio_mode=")[-1].strip()
        return ""