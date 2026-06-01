; ============================================================
; JarDiff Windows 安装程序脚本（Inno Setup 6.1+，需联网自动装依赖）
; 用法：先运行 build_windows.bat 生成 dist\JarDiff\，
;       再用 Inno Setup 打开本文件并 Build（或 ISCC.exe jardiff_inno.iss）。
; 产物：dist_installer\JarDiff-Setup-1.0.0.exe
;
; 安装时自动处理运行依赖：
;   - Microsoft Edge WebView2 Runtime：检测缺失则静默联网安装（运行必需）
;   - JDK 17：可选任务，勾选后自动下载并静默安装（反编译 .class 用）
; 需要 Inno Setup 6.1.0+（内置 DownloadTemporaryFile 联网下载）。
; ============================================================

#define MyAppName "JarDiff"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "JarDiff"
#define MyAppExeName "JarDiff.exe"

[Setup]
; 固定 AppId（升级时保持一致，勿改）
AppId={{8E2A6F31-2C4D-4B8E-9A1F-7D5C3B0E9A21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\JarDiff
DefaultGroupName=JarDiff
DisableProgramGroupPage=yes
OutputDir=..\dist_installer
OutputBaseFilename=JarDiff-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 64 位安装
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\jardiff_app\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
; 如本机 Inno 安装了简体中文语言包，可取消下一行注释：
; Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"
Name: "installjdk"; Description: "自动下载并安装 JDK 17（用于反编译 .class 源码，约 180MB，需联网）"; GroupDescription: "可选运行依赖:"; Flags: unchecked

[Files]
; 打包 PyInstaller 生成的整个 onedir 目录
Source: "..\dist\JarDiff\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\JarDiff"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 JarDiff"; Filename: "{uninstallexe}"
Name: "{autodesktop}\JarDiff"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 JarDiff"; Flags: nowait postinstall skipifsilent

[Code]
const
  WV2_CLIENT = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WV2_BOOTSTRAP_URL = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703';
  JDK_MSI_URL =
    'https://api.adoptium.net/v3/installer/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse';

function WebView2Installed: Boolean;
var
  pv: String;
begin
  Result := False;
  if RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + WV2_CLIENT, 'pv', pv) and (pv <> '') then
    Result := True
  else if RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WV2_CLIENT, 'pv', pv) and (pv <> '') then
    Result := True
  else if RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WV2_CLIENT, 'pv', pv) and (pv <> '') then
    Result := True;
end;

function JavaInstalled: Boolean;
var
  rc: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/C where javap >nul 2>nul', '',
    SW_HIDE, ewWaitUntilTerminated, rc) and (rc = 0);
end;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  rc: Integer;
begin
  if CurStep <> ssPostInstall then
    Exit;

  // 1) WebView2 Runtime（运行必需）：缺失则静默联网安装
  if not WebView2Installed then
  begin
    try
      DownloadTemporaryFile(WV2_BOOTSTRAP_URL, 'MicrosoftEdgeWebview2Setup.exe', '', @OnDownloadProgress);
      Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '',
        SW_HIDE, ewWaitUntilTerminated, rc);
    except
      MsgBox('WebView2 运行时自动安装失败，JarDiff 启动可能白屏。' + #13#10 +
             '请到微软官网手动安装 "Edge WebView2 Runtime" 后再运行。' + #13#10 +
             GetExceptionMessage, mbError, MB_OK);
    end;
  end;

  // 2) JDK（可选任务）：勾选且系统无 javap 时自动下载安装
  if WizardIsTaskSelected('installjdk') and not JavaInstalled then
  begin
    try
      DownloadTemporaryFile(JDK_MSI_URL, 'jdk17.msi', '', @OnDownloadProgress);
      Exec('msiexec.exe',
        '/i "' + ExpandConstant('{tmp}\jdk17.msi') + '" /quiet ' +
        'ADDLOCAL=FeatureMain,FeatureEnvironment,FeatureJavaHome',
        '', SW_HIDE, ewWaitUntilTerminated, rc);
    except
      MsgBox('JDK 自动安装失败，可稍后自行安装 JDK（仅反编译 .class 时需要）。' + #13#10 +
             GetExceptionMessage, mbError, MB_OK);
    end;
  end;
end;
