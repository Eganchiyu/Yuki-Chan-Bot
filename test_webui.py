import subprocess
import time
import requests

def test_webui():
    print("Starting WebUI server...")
    proc = subprocess.Popen(["python", "webui.py"])

    # Wait for the server to start (giving it more time)
    for i in range(10):
        time.sleep(2)
        try:
            resp = requests.get("http://localhost:1314")
            if resp.status_code == 200:
                print("WebUI is accessible and returns 200 OK.")
                break
        except Exception as e:
            print(f"Waiting for server... ({i+1}/10)")
    else:
        print("Error accessing WebUI: Could not connect within timeout.")

    print("Terminating WebUI server...")
    proc.terminate()
    proc.wait()
    print("WebUI server terminated.")

if __name__ == "__main__":
    test_webui()
