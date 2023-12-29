# app.py (Flask Server)

from flask import Flask, jsonify
from flask_cors import CORS
import subprocess
import os


app = Flask(__name__)
CORS(app)


@app.route('/run-script', methods=['POST'])
def run_script():
    try:
        # Save the current working directory
        original_dir = os.getcwd()

        # Change to the directory where main.py is located
        os.chdir('../')  # Adjust the path as needed

        result = subprocess.run(['python', 'main.py'], capture_output=True, text=True)
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)

        # Change back to the original directory
        os.chdir(original_dir)

        return jsonify({'status': 'Successfully Synced YT-Music Liked Songs to Spotify Liked', 'output': result.stdout}), 200
    except Exception as e:
        # Ensure we change back even if an error occurs
        os.chdir(original_dir)
        return jsonify({'status': 'error', 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(port=5000)
