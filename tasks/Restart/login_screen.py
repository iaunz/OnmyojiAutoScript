from tasks.Component.SwitchAccount.assets import SwitchAccountAssets
from tasks.GameUi.matcher import any_of
from tasks.Restart.assets import RestartAssets


# 旧版 8+ 标识有两种裁剪，重启、导航和切换账号共用这组登录页标识。
LOGIN_SCREEN = any_of(
    RestartAssets.I_LOGIN_16,
    RestartAssets.I_LOGIN_8,
    SwitchAccountAssets.I_CHECK_LOGIN_FORM,
)
