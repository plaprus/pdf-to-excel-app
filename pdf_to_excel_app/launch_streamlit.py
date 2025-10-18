import os, subprocess, sys

if __name__ == "__main__":
    app = os.path.join(os.path.dirname(__file__), "app.py")
    subprocess.run([sys.executable, "-m", "streamlit", "run", app], check=True)
