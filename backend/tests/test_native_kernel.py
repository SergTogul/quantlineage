import shutil, subprocess
from pathlib import Path
import pytest
from app.compute.kernel import Exposure, PythonScenarioKernel, Shock


def test_python_kernel_math():
    e=Exposure(delta=1000,gamma=200,vega=30,dv01=-10,fx_delta=500); s=Shock(-.1,5,20,-.02)
    expected=1000*(-.1)+.5*200*.01+30*5-10*20+500*(-.02)
    assert PythonScenarioKernel().pnl([e],[s]) == pytest.approx([expected])


def test_cpp_kernel_compiles_and_executes(tmp_path):
    if not shutil.which('g++'): pytest.skip('g++ unavailable')
    root=Path(__file__).parents[1]/'native'; exe=tmp_path/'kernel_test'
    subprocess.run(['g++','-std=c++20','-O2','-I',str(root/'include'),str(root/'tests/kernel_test.cpp'),'-o',str(exe)],check=True)
    result=subprocess.run([str(exe)],capture_output=True,text=True,check=True)
    assert 'risk_kernel_ok' in result.stdout


def test_native_ctypes_kernel_matches_python(tmp_path):
    if not shutil.which('g++'): pytest.skip('g++ unavailable')
    from app.compute.kernel import NativeScenarioKernel
    root=Path(__file__).parents[1]/'native'; lib=tmp_path/'libriskkernel.so'
    subprocess.run(['g++','-std=c++20','-O3','-shared','-fPIC',str(root/'src/risk_kernel_capi.cpp'),'-o',str(lib)],check=True)
    exposures=[Exposure(1000,200,30,-10,500),Exposure(-300,80,10,5,-200)]
    shocks=[Shock(-.1,5,20,-.02),Shock(.03,-2,-10,.01)]
    expected=PythonScenarioKernel().pnl(exposures,shocks)
    actual=NativeScenarioKernel(lib).pnl(exposures,shocks)
    assert actual == pytest.approx(expected)
