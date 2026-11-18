"""Build/run portable production codec with g++/clang++ or workspace-local Zig."""
from pathlib import Path
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def build():
    compiler=shutil.which("g++") or shutil.which("clang++")
    zig=ROOT/".test-tools/ziglang/zig.exe"
    if compiler: command=[compiler]
    elif zig.is_file(): command=[str(zig),"c++"]
    else: raise RuntimeError("Install g++/clang++ or workspace-local ziglang to run native firmware checks")
    out=ROOT/".native-build"; out.mkdir(exist_ok=True)
    binary=out/("packet_native.exe" if os.name=="nt" else "packet_native")
    subprocess.run([*command,"-std=c++11","-O2","-I",str(ROOT/"algorithm/firmware/common"),
                    str(ROOT/"algorithm/firmware/common/tests/packet_native.cpp"),"-o",str(binary)],check=True,cwd=ROOT)
    subprocess.run([str(binary)],check=True,cwd=ROOT)
    return binary


if __name__=="__main__": print(build())
