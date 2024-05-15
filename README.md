# MiniFreak Preset Viewer

MiniFreak Preset Viewer is a Python program that allows you to view the contents of preset files for the MiniFreak synthesizer. The program supports files with the `.mnfx` extension.

## Installation

1. Clone the repository or download the source code archive.
2. Install the required dependencies by running:
   

```sh
   pip install -r requirements.txt
   ```

## Usage

Run the program using Python, specifying the path to the pattern file. Example command:

```sh
python main.py [OPTIONS] FILENAME
```

### Options

* `FILENAME`: path to the `.mnfx` pattern file you want to view.

#### Available Options:

* `--sequence TEXT`: sequence of commands to parse the file.
* `--default_file TEXT`: path to the default preset file.
* `--show-all`: display all settings. Otherwise, only settings that are not in the default pattern file will be shown.
* `--hide-default-value`: hide default values.
* `--debug`: display debug information.
* `--directory-path TEXT`: path to the directory inside the zip archive where the file is located.
* `--format [yaml|compact]`: output format (yaml or compact).
* `--help`: show help message and exit.

### Usage Examples

View the contents of a file with all settings displayed:

```sh
python main.py --show-all path/to/file.mnfx
```

View the contents of a file in YAML format:

```sh
python main.py --format yaml path/to/file.mnfx
```

Run with debug information:

```sh
python main.py --debug path/to/file.mnfx
```

## License

This project is licensed under the MIT License. 
