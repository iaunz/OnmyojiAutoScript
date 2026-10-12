from copy import deepcopy

from module.atom.gif import RuleGif
from tasks.GlobalGame.assets import GlobalGameAssets


class GlobalGame(GlobalGameAssets):
    """Combine UI variants while keeping generated image definitions independent."""

    I_UI_REWARD = deepcopy(GlobalGameAssets.I_UI_REWARD)
    RuleGif.attach_to(I_UI_REWARD, [
        deepcopy(GlobalGameAssets.I_UI_REWARD),
        deepcopy(GlobalGameAssets.I_UI_REWARD_ALT),
    ])
