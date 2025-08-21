Shield: [![CC BY-NC-SA 4.0][cc-by-nc-sa-shield]][cc-by-nc-sa]

This work is licensed under a
[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License][cc-by-nc-sa].

[![CC BY-NC-SA 4.0][cc-by-nc-sa-image]][cc-by-nc-sa]

[cc-by-nc-sa]: http://creativecommons.org/licenses/by-nc-sa/4.0/
[cc-by-nc-sa-image]: https://licensebuttons.net/l/by-nc-sa/4.0/88x31.png
[cc-by-nc-sa-shield]: https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg

# ReactPyR

ReactPyR was developed to allow Python control of Mettler's ReactIR system via their iCIR software. 
This project was developed and tested using Windows 10 and on a ReactIR15 system and is written in Python3.13.0 using asyncua (pypi.org/project/asyncua/).All testing of ReactPyR was conducted with iCIR version 7.1.91 SP1 and iC OPC UA Client version 1.2.22. 

## Setup
Methods Path was obtained by connecting to the IR machine using UA expert and finding the Browse Name of each folder. Node IDs were obtained by connecting to the IR machine using UA Expert (v1.7.1) and obtaining XXX. 
 
![OPCUA](/images/OPCUA.PNG)


