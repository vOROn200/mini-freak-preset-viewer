import re
from natsort import natsorted
import xml.etree.ElementTree as ET
from functools import lru_cache
import click
import zipfile
import yaml

def get_file_descriptor(zip_path, directory_path):
    """
    Opens and returns the file descriptor of the first file found in the specified directory within a zip archive.
    
    :param zip_path: Path to the zip archive.
    :param directory_path: Path to the directory inside the zip archive where the file is located.
    :return: File descriptor of the first file found or None if no file is found or an error occurs.
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # List all items in the directory
            file_list = [f for f in zip_ref.namelist() if f.startswith(directory_path) and not f.endswith('/')]
            if file_list:
                # Return the file descriptor of the first file found
                return zip_ref.open(file_list[0])
            else:
                print("No file found in the specified directory.")
                return None
    except zipfile.BadZipFile:
        print("Failed to open the zip file.")
        return None
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return None

def scale_value(normalized_value, min_val, max_val):
    """ Приводит нормализованное значение от 0 до 1 к заданному диапазону min_val и max_val """
    return min_val + (max_val - min_val) * normalized_value

@lru_cache(maxsize=None)
def get_xml_root(xml_path):
    tree = ET.parse(xml_path)
    return tree.getroot()

def parse_xml_get_all_item_lists(xml_path):
    root = get_xml_root(xml_path)

    all_item_lists = {}

    for item_list in root.findall('./item_list'):
        item_list_name = item_list.get('name')
        current_list = [item.get('text') for item in item_list.findall('item')]
        all_item_lists[item_list_name] = current_list

    return all_item_lists

def parse_xml_find_param(xml_path, param_name, normalized_value, version="1.9.0"):
    root = get_xml_root(xml_path)

    all_item_lists = parse_xml_get_all_item_lists(xml_path)

    for param in root.findall(f".//param[@name='{param_name}']"):
        display_name = param.get('display_name')
        mapping_min = float(param.get('mapping-min', '0'))
        mapping_max = float(param.get('mapping-max', '1'))

        scaled_value = scale_value(normalized_value, mapping_min, mapping_max)

        item_list = None
        item_list = param.find(f".//item_list[@name='{param_name}_V{version}']")
            
        items = param.findall('item')

        if items:

            if items[0].get('from') is not None:
                return display_name, round(scaled_value)

            target_index = calculate_index_from_normalized_value(normalized_value, len(items))
            target_item = items[target_index]
            return display_name, target_item.get('text')
        
        if item_list is not None:
            items = all_item_lists[f"{param_name}_V{version}"]
            
            if items:
                target_index = calculate_index_from_normalized_value(normalized_value, len(items))
                target_item = items[target_index]   
                return display_name, target_item

        return display_name, round(scaled_value * 100, 1)
    return None, None

def find_display_value(xml_paths, key, value):
    for path in xml_paths:
        display_name, display_value = parse_xml_find_param(path, key, value)
        if display_value is not None:
            return display_name, display_value
    return None, None


def parse_string_with_regex(s):
    pattern = re.compile(r'(\d+) (\w+) ([^ ]+)')
    
    result = {}
    
    matches = pattern.finditer(s)
    for match in matches:
        key_length, key, value = match.groups()
        key_length = int(key_length)
        
        if len(key) == key_length:
            result[key] = value
    
    return result

def read_until_zero_byte(file, offset):
    file.seek(offset)

    result_bytes = bytearray()
    while True:
        byte = file.read(1)
        if byte == b'\x01' or not byte:
            break
        result_bytes.extend(byte)

    result_string = result_bytes.decode('utf-8', 'ignore')

    return result_string


def read_fixed_length_token(file, start_index):
    file.seek(start_index)
    data = file.read(1024) 
    space_index = data.find(b' ')
    token_length = int(data[:space_index]) 
    if token_length == 0:
        new_index = start_index + space_index + 1
        file.seek(new_index)
        if file.read(1) == b' ':
            new_index += 1
        return '', new_index
    token = data[space_index + 1:space_index + 1 + token_length].decode('utf-8')
    new_index = start_index + space_index + 1 + token_length
    file.seek(new_index)
    if file.read(1) == b' ':
        new_index += 1

    return token, new_index


def skip_words(file, num_words):
    in_word = False
    while num_words > 0:
        byte = file.read(1)
        if not byte: 
            break

        if byte == b' ':
            if in_word: 
                num_words -= 1
            in_word = False
        else:
            in_word = True

    while True:
        next_char = file.read(1)
        if next_char != b' ' or not next_char:
            file.seek(-1, 1)
            break

    return file.tell()

def process_hash_commands_until_index(file, start_index, end_index):
    metadata = {}
    current_index = start_index
    
    while current_index < end_index:
        key, new_index = read_fixed_length_token(file, current_index)
        if new_index >= end_index or not key:
            break
        value, new_index = read_fixed_length_token(file, new_index)
        if new_index >= end_index or not value:
            break
        metadata[key] = value
        current_index = new_index

    return metadata

def find_sequence_of_digit_tokens(file, num_tokens, start_index):
    file.seek(start_index)
    count_digits_tokens = 0
    current_token = []
    in_token = False

    start_index_of_sequence = None 
    end_index_of_sequence = None
    previous_char_was_space = True

    while True:
        byte = file.read(1)
        if not byte:
            break
        
        if byte == b' ':
            if in_token:
                if all(c.isdigit() for c in current_token):
                    count_digits_tokens += 1
                    if count_digits_tokens == 1:
                        start_index_of_sequence = file.tell() - len(current_token) - 1
                    if count_digits_tokens == num_tokens:
                        end_index_of_sequence = file.tell() - 1
                        return start_index_of_sequence, end_index_of_sequence
                else:
                    count_digits_tokens = 0
                current_token = []
            in_token = False
            previous_char_was_space = True
        else:
            if not in_token:
                in_token = True
            current_token.append(byte.decode('utf-8'))
            previous_char_was_space = False

    return None, None

def parse_file(file, sequence):
    metadata = {}
    file_size = file.seek(0, 2)
    i = 0
    commands = sequence.split()
    command_index = 0

    while i < file_size and command_index < len(commands):
        command = commands[command_index]
        
        if command == '_':
            _, i = read_fixed_length_token(file, i)
        elif command.isdigit():
            i = skip_words(file, int(command))
        elif command.startswith('#*'):
            num_words = int(command[2:-1])
            begin_index_digit, end_index_digit = find_sequence_of_digit_tokens(file, num_words, i)
            if begin_index_digit is not None and end_index_digit is not None:
                metadata.update(process_hash_commands_until_index(file, i, begin_index_digit))
                i = end_index_digit

        elif command == '#':
            key, i = read_fixed_length_token(file, i)
            value, i = read_fixed_length_token(file, i)
            metadata[key] = value
        elif command.isalpha():
            predefined_keys = {'N': 'Name', 'B': 'Bank', 'D': 'Designer', 'T': 'Text', 'V': 'Version'}
            key = predefined_keys.get(command)
            if key:
                value, i = read_fixed_length_token(file, i)
                metadata[key] = value
        command_index += 1

    return i, metadata

def display_setting_yaml(key, value, display_current_value, default_value, display_default_value, percent_change, 
                         current_value, default_numeric_value, display_current_name=None, 
                         show_current_value=True, show_default_value=True, show_percent_change=True, debug=False, compact=False):
    
    output = {}
    
    if display_current_name:
        output['display_name'] = display_current_name
    
    if show_current_value:
        display_current_value = f"{display_current_value}"
        output['display_value'] = display_current_value
        if debug:
            output['raw_value'] = value
        
    if show_default_value and default_numeric_value is not None and default_value is not None:
        output['display_default_value'] = display_default_value
        if debug:
            output['default_raw_value'] = default_value
        if show_percent_change:
            output['percent_change'] = f"{percent_change}%"
    
    if compact:
        if debug:
            output = value
        else:
            output = display_current_value

    print(yaml.dump({key: output}, default_flow_style=False, sort_keys=False), end='')

def calculate_index_from_normalized_value(normalized_value, num_items):
    if not (0 <= normalized_value <= 1):
        raise ValueError("Normalized value must be between 0 and 1.")
    
    if num_items <= 0:
        raise ValueError("Number of items must be greater than 0.")
    
    index = round(normalized_value * (num_items - 1))
    
    return index

@click.command()
@click.argument('filename')
@click.option('--sequence', default="_ 5 N B 1 D _ 6 T 1 V 14 #*14D", help='Sequence of commands to parse the file')
@click.option('--default_file', default='data/Default', help='Path to the default preset file')
@click.option('--show-all', is_flag=True, default=False, help="Display all settings. Otherwise, only settings that are not in the default pattern file will be shown")
@click.option('--hide-default-value', is_flag=True, default=False, help="Hide default value")
@click.option('--debug', is_flag=True, default=False, help="Display debug information")
@click.option('--directory-path', default='MiniFreak/', help='Path to the directory inside the zip archive where the file is located')
@click.option('--format', type=click.Choice(['yaml', 'compact'], case_sensitive=False), default='yaml', help="Output format")
def process_file(filename, default_file, sequence, show_all, debug, hide_default_value, directory_path, format):
    sorted_parsed_data_default = {}
    with open(default_file, 'rb') as file: 
        index, metadata = parse_file(file, sequence)
        offset = index + 1  
        input_string = read_until_zero_byte(file, offset)
        parsed_data = parse_string_with_regex(input_string)
        sorted_parsed_data_default = dict(natsorted(parsed_data.items()))

    file = get_file_descriptor(filename, directory_path)

    index, metadata = parse_file(file, sequence)
    offset = index + 1
    input_string = read_until_zero_byte(file, offset)
    parsed_data = parse_string_with_regex(input_string)
    sorted_parsed_data = natsorted(parsed_data.items())
    print(yaml.dump({"Metadata": metadata}, default_flow_style=False, sort_keys=False), end='')

    xml_path = 'data/minifreak_vst_params.xml'
    xml_path2 = 'data/minifreak_internal_params.xml'
    xml_path3 = 'data/minifreak_fx_presets_params.xml'

    xml_paths = [xml_path, xml_path2, xml_path3]
    memory = {}

    for key, value in sorted_parsed_data:
        try:
            current_value = float(value)
            default_value = sorted_parsed_data_default.get(key)
            default_numeric_value = float(default_value) if default_value is not None else None

            display_current_name, display_current_value = find_display_value(xml_paths, key, current_value)
            if default_numeric_value is not None:
                display_default_name, display_default_value = find_display_value(xml_paths, key, default_numeric_value)
            else:
                display_default_name = None
                display_default_value = None

            # save fx_option value
            key_to_save = ["FX1_Opt1", "FX1_Opt2", "FX1_Opt3", "FX2_Opt1", "FX2_Opt2", "FX2_Opt3", "FX3_Opt1", "FX3_Opt2", "FX3_Opt3"]
            if key in key_to_save:
                memory[key] = value

            if show_all or current_value != default_numeric_value:
                if default_numeric_value is not None and default_numeric_value != 0:
                    percent_change = round(((current_value - default_numeric_value) / default_numeric_value) * 100)
                    if format == 'yaml':
                        display_setting_yaml(key, value, display_current_value, default_value, display_default_value, percent_change, current_value, default_numeric_value, display_current_name, debug=debug, show_default_value=not hide_default_value)
                    else:
                        display_setting_yaml(key, value, display_current_value, default_value, display_default_value, percent_change, current_value, default_numeric_value, display_current_name, debug=debug, show_default_value=not hide_default_value, compact=True)
                else:
                    if format == 'yaml':
                        display_setting_yaml(key, value, display_current_value, default_value, display_default_value, None, current_value, default_numeric_value, display_current_name, show_percent_change=False, debug=debug, show_default_value=not hide_default_value)
                    else:
                        display_setting_yaml(key, value, display_current_value, default_value, display_default_value, None, current_value, default_numeric_value, display_current_name, show_percent_change=False, debug=debug, show_default_value=not hide_default_value, compact=True)
            key_to_gen = ["FX1_Type", "FX2_Type", "FX3_Type"]
            if key in key_to_gen:
                index = key_to_gen.index(key) + 1

                new_key_gen = f"FX{index}_Opt1"
                new_value_gen = memory.get(new_key_gen)
                new_key = ""
                if display_current_value == "Delay":
                    new_key = f"Opt{index}_StereoDelay"
                else:    
                    new_key = f"Opt{index}_{display_current_value}"

                if value is not None:
                    new_display_current_name, new_display_current_value = find_display_value(xml_paths, new_key, float(new_value_gen))
                        
                    if debug:
                        output = float(new_value_gen)
                    else:
                        output = new_display_current_value

                    print(yaml.dump({new_key: output}, default_flow_style=False, sort_keys=False), end='')
        except ValueError:
            pass
if __name__ == '__main__':
    process_file()