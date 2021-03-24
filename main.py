import json
import os
import sys
from dotenv import load_dotenv
from PyQt5 import QtWidgets as qtw, QtGui as qtg, QtCore as qtc, uic
from SpotLibrarian.SpotLibrarian import SpotLibrarian



if __name__ == "__main__":
    load_dotenv()
    app = qtw.QApplication(sys.argv)  # Create an instance of QtWidgets.QApplication
    window = SpotLibrarian(os.getenv("CLIENT_SECRET"))  # Create an instance of our class
    app.exec_()  # Start the application
