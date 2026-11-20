# Python Chat Application (Socket Programming)

Two-way chat between a **server** and a **client** using Python sockets and a Tkinter window.
No extra libraries needed - only Python 3.8+ (Tkinter comes with the standard Windows/macOS installer).

## Files

| File        | Purpose                                              |
|-------------|------------------------------------------------------|
| `server.py` | Server window - listens for a client, chats with it  |
| `client.py` | Client window - connects to the server, chats        |

## How to run in VS Code

1. `File > Open Folder...` and open the `chat_app` folder.
2. Open a terminal: `Terminal > New Terminal`.
3. Run the server (**first**):
   ```
   python server.py
   ```
4. Click the **Split Terminal** icon in the terminal panel, then run the client in the new terminal:
   ```
   python client.py
   ```
5. Type in either window and press **Enter** or click **Send**.

(If `python` is not found on Windows, use `py server.py` and `py client.py`.)

## Notes

* Start `server.py` before `client.py`. If you forget, the client shows a message - just start the server and click **Connect**.
* Both files use `HOST = "127.0.0.1"` and `PORT = 12345`. If the port is busy, change `PORT` in **both** files.
* To chat between two different computers, set `HOST` in `client.py` to the server computer's IP address,
  and set `HOST = "0.0.0.0"` in `server.py`.
