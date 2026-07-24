from flask import Flask, jsonify
from flask_cors import CORS
import subprocess
import sys
from pathlib import Path


app = Flask(__name__)
CORS(app)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@app.route("/run-script", methods=["POST"])
def run_script():
    try:
        result = subprocess.run(
            [sys.executable, "main.py"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)

        if result.returncode != 0:
            return jsonify(
                {
                    "status": "error",
                    "output": result.stdout,
                    "error": result.stderr,
                }
            ), 500

        return jsonify(
            {
                "status": "Successfully synced liked songs",
                "output": result.stdout,
            }
        ), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


if __name__ == "__main__":
    app.run(port=5000)
