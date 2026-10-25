## Why?
I was playing with my recently unlocked Motorola E13 and i stumbled upon the logo partition, I thought it would be fun to tell the AI to reverse engineer the original logo.bin and make me a python program to be able to change the logos to my liking.

## Usage
**IMPORTANT:** You must unlock the bootloader on the Motorola E13 using the [CVE-2022-38694](https://github.com/TomKing062/CVE-2022-38694_unlock_bootloader) before attempting this mod, otherwise the phone may result in a bootloop.

- Usage:
  
```
   python3 logotool.py info logo.bin
   python3 logotool.py unpack logo.bin <Folder>
   python3 logotool.py pack <Folder> new_logo.bin [--resize]
   python3 logotool.py verify logo.bin (unpack + pack)
```

### Steps:
  
1. Clone the repo ```git clone https://github.com/MeLlamoGamer/MotorolaE13_BootLogo_Changer```
2. Unpack the logo.bin obtained from the original firmware(This can be obtained using Motorola's RSA).
3. Modify the bmp's as you like **without changing neither the file name nor the original image resolution.**
4. Pack the folder containing the modified bmp files.
5. Enter fastboot mode:
   
   **From android using adb**: ```adb reboot bootloader```

   **With the phone turned off**: Press vol- and power at the same time until it boots
6. Use the fastboot that comes with this repo and flash the two logo partitions as following:
   ```
   fastboot.exe flash logo <new_logo.bin>
   fastboot.exe flash fbootlogo <new_logo.bin>
   ```
7. **Enjoy!**


## DISCLAIMER
### USE AT YOUR OWN RISK.
By using this tool, flashing the resulting modified ```logo.bin``` to your device, or unlocking your bootloader, you acknowledge and accept full responsibility for any outcomes.
The author and contributors of this repository are not responsible for any damage to your phone, data loss, or any other liabilities arising from the use of this tool. Ensure you know what you are doing and follow instructions carefully.
   

