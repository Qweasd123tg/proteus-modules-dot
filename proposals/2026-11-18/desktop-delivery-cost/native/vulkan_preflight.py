"""Test Vulkan device discovery, without opening a window."""
from ctypes import *
vk=CDLL("libvulkan.so.1")
class Info(Structure):
    _fields_=[("sType",c_int),("pNext",c_void_p),("flags",c_uint32),("app",c_void_p),
              ("layers",c_uint32),("names",c_void_p),("ext",c_uint32),("extensions",c_void_p)]
info=Info(); info.sType=1; handle=c_void_p()
vk.vkCreateInstance.argtypes=[POINTER(Info),c_void_p,POINTER(c_void_p)]
r=vk.vkCreateInstance(byref(info),None,byref(handle))
print("vkCreateInstance",r)
if r: raise SystemExit(1)
n=c_uint32()
vk.vkEnumeratePhysicalDevices.argtypes=[c_void_p,POINTER(c_uint32),c_void_p]
r=vk.vkEnumeratePhysicalDevices(handle,byref(n),None)
print("vkEnumeratePhysicalDevices",r,"count",n.value)
vk.vkDestroyInstance.argtypes=[c_void_p,c_void_p]
vk.vkDestroyInstance(handle,None)
