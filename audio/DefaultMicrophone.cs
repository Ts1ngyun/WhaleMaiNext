using System;
using System.Runtime.InteropServices;

// Windows Core Audio: select the active VB-CABLE capture endpoint, not playback.
[ComImport,Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMEnumerator {}
[ComImport,Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMEnumerator {
 [PreserveSig]int EnumAudioEndpoints(int flow,uint state,out IMMCollection devices);
 [PreserveSig]int GetDefaultAudioEndpoint(int flow,int role,out IMMDevice device);
 [PreserveSig]int GetDevice([MarshalAs(UnmanagedType.LPWStr)]string id,out IMMDevice device);
 [PreserveSig]int RegisterEndpointNotificationCallback(IntPtr p);
 [PreserveSig]int UnregisterEndpointNotificationCallback(IntPtr p);
}
[ComImport,Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMCollection {
 [PreserveSig]int GetCount(out uint count);
 [PreserveSig]int Item(uint index,out IMMDevice device);
}
[ComImport,Guid("D666063F-1587-4E43-81F1-B948E807363F"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice {
 [PreserveSig]int Activate(ref Guid iid,uint ctx,IntPtr parameters,[MarshalAs(UnmanagedType.IUnknown)]out object obj);
 [PreserveSig]int OpenPropertyStore(uint mode,out IPropertyStore store);
 [PreserveSig]int GetId([MarshalAs(UnmanagedType.LPWStr)]out string id);
 [PreserveSig]int GetState(out uint state);
}
[StructLayout(LayoutKind.Sequential)]struct PropertyKey {public Guid fmtid;public uint pid;}
[StructLayout(LayoutKind.Explicit)]struct PropVariant {
 [FieldOffset(0)]public ushort vt;[FieldOffset(8)]public IntPtr value;
 [FieldOffset(16)]public long padding;
}
[ComImport,Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IPropertyStore {
 [PreserveSig]int GetCount(out uint count);
 [PreserveSig]int GetAt(uint index,out PropertyKey key);
 [PreserveSig]int GetValue(ref PropertyKey key,out PropVariant value);
 [PreserveSig]int SetValue(ref PropertyKey key,ref PropVariant value);
 [PreserveSig]int Commit();
}
[ComImport,Guid("870AF99C-171D-4F9E-AF0D-E63DF40C2BC9")]class PolicyConfig {}
[ComImport,Guid("F8679F50-850A-41CF-9C72-430F290290C8"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IPolicyConfig {
 [PreserveSig]int GetMixFormat(string id,IntPtr format);
 [PreserveSig]int GetDeviceFormat(string id,int def,IntPtr format);
 [PreserveSig]int ResetDeviceFormat(string id);
 [PreserveSig]int SetDeviceFormat(string id,IntPtr endpoint,IntPtr mix);
 [PreserveSig]int GetProcessingPeriod(string id,int def,IntPtr defPeriod,IntPtr minPeriod);
 [PreserveSig]int SetProcessingPeriod(string id,IntPtr period);
 [PreserveSig]int GetShareMode(string id,IntPtr mode);
 [PreserveSig]int SetShareMode(string id,IntPtr mode);
 [PreserveSig]int GetPropertyValue(string id,ref PropertyKey key,out PropVariant value);
 [PreserveSig]int SetPropertyValue(string id,ref PropertyKey key,ref PropVariant value);
 [PreserveSig]int SetDefaultEndpoint([MarshalAs(UnmanagedType.LPWStr)]string id,int role);
 [PreserveSig]int SetEndpointVisibility(string id,int visible);
}
public static class DefaultMicrophone {
 [DllImport("ole32.dll")]static extern int PropVariantClear(ref PropVariant value);
 static void Check(int hr){Marshal.ThrowExceptionForHR(hr);}
 static string Name(IMMDevice device){
  IPropertyStore store;Check(device.OpenPropertyStore(0,out store));
  PropertyKey key=new PropertyKey{fmtid=new Guid("A45C254E-DF1C-4EFD-8020-67D146A850E0"),pid=14};
  PropVariant val;Check(store.GetValue(ref key,out val));
  try{return val.vt==31?Marshal.PtrToStringUni(val.value):"";}finally{PropVariantClear(ref val);}
 }
 public static string Ensure(bool apply){
  IMMEnumerator en=(IMMEnumerator)new MMEnumerator();IMMCollection devices;Check(en.EnumAudioEndpoints(1,1,out devices));
  uint count;Check(devices.GetCount(out count));string selected=null;int matches=0;
  for(uint i=0;i<count;i++){IMMDevice d;Check(devices.Item(i,out d));if(string.Equals(Name(d),"CABLE Output (VB-Audio Virtual Cable)",StringComparison.OrdinalIgnoreCase)){Check(d.GetId(out selected));matches++;}}
  if(matches!=1)throw new InvalidOperationException("Expected exactly one active CABLE Output capture device; found "+matches);
  IPolicyConfig policy=apply?(IPolicyConfig)new PolicyConfig():null;
  for(int role=0;role<3;role++){
   IMMDevice d;int hr=en.GetDefaultAudioEndpoint(1,role,out d);string current=null;
   if(hr>=0)Check(d.GetId(out current));
   if(current!=selected){if(!apply)return "not-selected";Check(policy.SetDefaultEndpoint(selected,role));}
  }
  for(int role=0;role<3;role++){IMMDevice d;string id;Check(en.GetDefaultAudioEndpoint(1,role,out d));Check(d.GetId(out id));if(id!=selected)throw new InvalidOperationException("Default microphone verification failed");}
  return "CABLE Output verified for all recording roles";
 }
}
