Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Ensure headless mode so no desktop popup windows appear
WshShell.Environment("PROCESS")("ELEPHANT_HEADLESS") = "1"

' Launch server silently in the background (0 = hidden window)
WshShell.Run "cmd /c cd /d """ & strDir & """ && python server.py", 0, False

' Wait 2.5 seconds for the Flask server to initialize
WScript.Sleep 2500

' Open the web application dashboard in your default browser
WshShell.Run "http://127.0.0.1:5000"
