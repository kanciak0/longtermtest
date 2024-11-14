#!/usr/bin/env python
# This Python file uses the following encoding: utf-8

import os
import socket
import binascii
import time
from datetime import datetime
import configparser

# Inicjalizuj liczniki udanych i nieudanych odczytów
successful_reads = 0
error_reads = 0
timeout_reads = 0
partial_reads = 0
no_response = 0

# Sprawdzenie, czy plik istnieje
config_file = 'odczyt_licznika.ini'
if not os.path.exists(config_file):
  # Plik nie istnieje, więc go tworzymy z domyślnymi wartościami
  config = configparser.ConfigParser()

  # Dodanie sekcji DEFAULT z domyślnymi wartościami
  config['CONFIG'] = {
    'ip_address': '192.168.0.1',
    'port': '2002',
    'log_dir': './',
    'socket_timeout': '5',
    'num_retries': '15000',
    'delay_between_runs': '5'
    }

  # Zapisanie domyślnych wartości do nowego pliku konfiguracyjnego
  with open(config_file, 'w') as configfile:
    config.write(configfile)

else:
  # Plik istnieje, więc go wczytujemy
  config = configparser.ConfigParser()
  config.read(config_file)

def send_and_receive_hex_data_tcp(hex_data_list, ip_address, port):
  global successful_reads, partial_reads, no_response, error_reads, timeout_reads, socket_timeout # Informacja, że używamy zmiennych globalnych

  # Utwórz gniazdo TCP
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

  # Ustaw timeout dla operacji na gnieździe (w sekundach)
  sock.settimeout(socket_timeout)  # Przykładowy timeout: 5 sekund

  try:
    # Wyzeruj licznik odczytów w pętli oraz flagę błędów
    reads_count = 0
    error_flag = 0

    # Połącz się z określonym adresem IP i portem
    sock.connect((ip_address, port))

    for hex_data in hex_data_list:
      # Przekonwertuj dane szesnastkowe na bajty
      binary_data = binascii.unhexlify(hex_data)

      # Wyślij dane
      sock.sendall(binary_data)

      try:
        # Odbierz odpowiedź (maksymalny rozmiar bufora to 2048 bajtów)
        received_data = sock.recv(2048)

        if received_data:
	  # Przekonwertuj otrzymane dane na format szesnastkowy
          hex_received_data = binascii.hexlify(received_data).decode('utf-8')

          print("Received data:", str(hex_received_data))
          plik.write('Received data: '+str(hex_received_data)+'\n')

          # Zwiększ licznik udanych odczytów
          reads_count += 1

      except socket.timeout:
        print("Received data: Meter did not respond.")
        plik.write('Received data: Meter did not respond.'+'\n')

  except socket.timeout:
    timeout_reads += 1
    error_flag += 1
    print("Error: TCP connection timeout.")
    plik.write('Error: TCP connection timeout.'+'\n')

  except socket.error as e:
    error_reads += 1
    error_flag += 1
    print("Error: ",str(e))
    plik.write('Error: '+str(e)+'\n')

  finally:
    # Zamknij gniazdo
    sock.close()

    # Statystyka liczby odczytów
    # if reads_count == 3 and error_flag == 0: 
    if reads_count == 2 and error_flag == 0: # Zmiana po wyłączeniu "Readout"
      successful_reads += 1
    # elif reads_count in [1,2] and error_flag == 0:
    elif reads_count in [1] and error_flag == 0: # Zmiana po wyłączeniu "Readout"
      partial_reads += 1
    else:
      if reads_count == 0 and error_flag == 0:
        no_response += 1

  # Zwróć liczbę udanych i błędnych odczytów
  return successful_reads, partial_reads, no_response, error_reads, timeout_reads

# Lista danych do wysłania w formacie szesnastkowym
data_to_send_hex_list = [
  "000100010001003F603DA109060760857405080101A90504034447548A0207808B0760857405080201AC0A80083031323334353637BE10040E01000000065F1F040000FFFFFFFF",  # Connect
  # "0001000100010040C003C1060007000015000BFF03000007000015000BFF04000007000015000BFF05000007000015000BFF06000007000015000BFF07000007000015000BFF0800",  # Readout (wyłączony, ponieważ licznik odpowiada zmiennyumi kluczami)
  "00010001000100056203800100",  # Disconnect
]

# TCP socket timeout
socket_timeout = config['CONFIG'].getint('socket_timeout')

# Katalog do zapisu logów
log_dir = config['CONFIG']['log_dir']

# Adres IP i port odpytywanego licznika
ip_address = config['CONFIG']['ip_address']
port = config['CONFIG'].getint('port')

# Liczba powtórzeń i opóźnienie (w sekundach) przed kolejnym wykonaniem
num_retries = config['CONFIG'].getint('num_retries')
delay_between_runs = config['CONFIG'].getint('delay_between_runs')  # Opóźnienie: 5 sekund

# Wyświetlenie wartości zmiennych konfiguracyjnych
print("##############################")
print("CONFIG section:")
print("ip_address: ", str(ip_address))
print("port: ", str(port))
print("log_dir: ", str(log_dir))
print("socket_timeout: ", str(socket_timeout))
print("num_retries: ", str(num_retries))
print("delay_between_runs: ", str(delay_between_runs))
print("##############################")

# Pętla wykonująca funkcję z określoną liczbą powtórzeń i opóźnieniem oraz zapisująca zdarzenia do pliku
for counter in range(1,num_retries+1):
  current_timestamp = time.time()
  formatted_timestamp = datetime.fromtimestamp(current_timestamp).strftime('%Y-%m-%d %H:%M:%S')
  file_name = str(log_dir)+datetime.fromtimestamp(current_timestamp).strftime('%Y-%m-%d_odczyt_licznika'+'.txt')
  plik = open(file_name, 'a')
  print("Timestamp:", str(formatted_timestamp))
  plik.write('Timestamp: '+str(formatted_timestamp)+'\n')
  successful_reads, partial_reads, no_response, error_reads, timeout_reads = send_and_receive_hex_data_tcp(data_to_send_hex_list, ip_address, port)
  print("Loop counter: ", str(counter),"/",str(num_retries))
  plik.write('Loop counter: '+str(counter)+'/'+str(num_retries)+'\n')

  if counter != 0:
    percent = (float(successful_reads) / counter) * 100
    print("Meter reading accuracy: {:.2f}%".format(percent))
    plik.write('Meter reading accuracy: {:.2f}%\n'.format(percent))
  else:
    print("Error: The variable [counter] must have a non-zero value.")
    plik.write('Error: The variable [counter] must have a non-zero value.')

  print("Successful meter readings:", str(successful_reads))
  plik.write('Successful meter readings: '+str(successful_reads)+'\n')
  print("Incomplete meter readings:", str(partial_reads))
  plik.write('Incomplete meter readings: '+str(partial_reads)+'\n')
  print("Meter not responding:", str(no_response))
  plik.write('Meter not responding: '+str(no_response)+'\n')
  print("TCP connection error:", str(error_reads))
  plik.write('TCP connection error: '+str(error_reads)+'\n')
  print("TCP timeout error:", str(timeout_reads))
  plik.write('TCP timeout error: '+str(timeout_reads)+'\n')
  print("---------------------------------------------")
  plik.write('---------------------------------------------'+'\n')
  plik.close()
  time.sleep(delay_between_runs)
