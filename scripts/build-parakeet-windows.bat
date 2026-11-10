@echo off
rem Builds parakeet.dll (+ ggml*.dll) from the whisper.cpp fork into whisper.cpp\build-shared\bin.
rem CPU-only by default. For GPU, pass extra CMake flags, e.g.:
rem   scripts\build-parakeet-windows.bat -DGGML_CUDA=ON      (needs CUDA Toolkit)
rem   scripts\build-parakeet-windows.bat -DGGML_VULKAN=ON    (needs Vulkan SDK)
setlocal
set "VS=C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools"
call "%VS%\VC\Auxiliary\Build\vcvars64.bat" || exit /b 1
set "PATH=%VS%\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin;%APPDATA%\Python\Python313\Scripts;%PATH%"
cd /d "%~dp0..\whisper.cpp" || exit /b 1
cmake -B build-shared -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON ^
  -DWHISPER_BUILD_EXAMPLES=OFF -DWHISPER_BUILD_TESTS=OFF %* || exit /b 1
cmake --build build-shared --target parakeet -j 8 || exit /b 1
echo.
dir /b build-shared\bin\*.dll
