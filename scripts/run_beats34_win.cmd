@echo off
"C:\Program Files\Git\usr\bin\mintty.exe" -o FontHeight=16 -o Columns=140 -o Rows=40 -w max -e /usr/bin/bash -l -c "cd /c/Users/bendu/qwen-memoryagent && bash scripts/demo_beats34.sh; echo; echo === DONE ===; sleep 4"
