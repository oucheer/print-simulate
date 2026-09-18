@echo off
"C:\Windows\System32\ping.exe" -n 1 127.0.0.1
 -netdev "user,id=n1,hostfwd=tcp::515-:515,hostfwd=tcp::631-:631"
