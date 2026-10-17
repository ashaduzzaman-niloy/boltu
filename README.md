----------------------TO RUN BOLTU THROUGH TERMINAL----------------------

Step 1: Create a folder in any directory of your PC.

Step 2: Inside the directory, create these folders:
	chats, config, engine, models, src

Step 3: Download boltu_core.py and boltu_gui.py and insert them in the src folder.

Step 4: Downlaod llama server files from https://github.com/ggml-org/llama.cpp/releases and extract them in the engine folder.

Step 5: Download any qwen model file from https://huggingface.co/collections/ggml-org/qwen-3 in the models folder.

Step 6: Open terminal and go to the src directory. Then run the following code:
	py boltu_gui.py

----------------------TO CONVERT BOLTU TO AN APP----------------------

Open the directory with all python folders in terminal.

Step 1: py -m venv .venv

Step 2: \.venv\Scripts\python.exe -m pip install --upgrade pip

Step 3: \.venv\Scripts\python.exe -m pip install PySide6 matplotlib numpy pyinstaller

Step 4: \.venv\Scripts\pyinstaller.exe --clean --onedir --windowed --name Boltu --icon Boltu.ico --add-data "Boltu.ico;." --paths src src\boltu_gui.py

----------------------TO RUN BOLTU AS AN APP----------------------

Step 1: Download and extract this file https://drive.google.com/file/d/1ozlUfxjqqLQXpWKIZKQStSARhuKBa1rF
