# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import time
import re
from cached_property import cached_property

from tasks.base_task import BaseTask
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_realm_raid, page_main, page_shikigami_records
from tasks.RealmRaid.assets import RealmRaidAssets
from tasks.RealmRaid.config import RealmRaid, RaidMode, AttackNumber, WhenAttackFail
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.Component.GeneralBattle.battle_wait import battle_wait_strategy


from module.logger import logger
from module.exception import GameOcrError, TaskEnd
from module.atom.image_grid import ImageGrid
from module.atom.image import RuleImage
from module.atom.click import RuleClick


class ScriptTask(GeneralBattle, GameUi, SwitchSoul, RealmRaidAssets):
    medal_grid: ImageGrid = None
    TICKET_OCR_RETRIES = 10

    def run(self):
        self.run_2()

    def is_ticket(self) -> bool:
        """
        如果没有票了，那么就返回False
        :return:
        """
        return self.check_ticket()

    def medal_fire(self) -> bool:
        """
        点击勋章
        :return:
        """
        # 点击勋章的挑战 和挑战
        time.sleep(0.2)
        is_click = False
        while 1:
            self.screenshot()

            if self.appear(self.I_FIRE, threshold=0.8):
                break

            if self.appear_then_click(self.I_SOUL_RAID, interval=1.5):
                while 1:
                    self.screenshot()
                    if self.appear_then_click(self.I_SOUL_RAID, interval=1.5):
                        continue
                    if not self.appear(self.I_SOUL_RAID, threshold=0.6):
                        break
                continue

            target = self.medal_grid.find_anyone(self.device.image)
            if target:
                self.appear_then_click(target, interval=2)  # 点击勋章,但是设置为两秒的间隔，适应不同的模拟器速度
                is_click = not is_click

            if is_click:
                continue
        logger.info(f'Click Medal')

        # 点击挑战
        self.wait_until_appear(self.I_FIRE)
        while 1:
            self.screenshot()
            if self.appear_then_click(self.I_FIRE, interval=2):
                continue
            if not self.appear(self.I_FIRE, threshold=0.8):
                break
        logger.info(f'Click {self.I_FIRE.name}')

    def execute_round(self, config: RealmRaid) -> bool:
        """
        执行一轮 除非票不够，一直到到九次
        :return:
        """
        # 如果没有票了，就退出
        if not self.is_ticket():
            return False

        # 判断是退四打九还是全部打
        if config.raid_config.raid_mode == RaidMode.NORMAL:
            logger.info(f'Execute round, retreat four attack nine')
            self.medal_fire()
            self.run_general_battle_back(config.general_battle_config)

            self.medal_fire()
            self.run_general_battle_back(config.general_battle_config)

            self.medal_fire()
            self.run_general_battle_back(config.general_battle_config)

            self.medal_fire()
            self.run_general_battle_back(config.general_battle_config)

        # 打九次
        for i in range(9):
            if not self.is_ticket():
                return False
            self.medal_fire()
            self.run_general_battle(config.general_battle_config)
            self.wait_until_appear(self.I_BACK_RED)

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def run_2(self):
        con = self.config.realm_raid
        if con.switch_soul_config.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(con.switch_soul_config.switch_group_team)
        if con.switch_soul_config.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(con.switch_soul_config.group_name, con.switch_soul_config.team_name)

        self.goto_page(page_realm_raid)

        # 有呱太活动的时候第一次进入还会 出现一个弹窗
        self.screenshot()
        if self.appear(self.I_FROG_RAID):
            logger.info(f'Click {self.I_FROG_RAID.name}')
            while 1:
                self.screenshot()
                if not self.appear(self.I_FROG_RAID):
                    break
                if self.appear_then_click(self.I_FROG_RAID, interval=1):
                    continue
        # 判断是不是锁定阵容
        self.ensure_lock(con.general_battle_config.lock_team_enable)
        # 判断是否是呱太活动
        frog = self.is_frog(True)
        if frog:
            logger.info(f'Frog raid')


        # 开始循环
        success = True
        last_battle = True  # 记录上一次战斗的结果
        successful_count = 0
        # 更改循环顺序
        while 1:
            self.screenshot()
            #看到弹窗点掉，不然会卡死
            if self.appear(self.I_FRESH_ENSURE):
                logger.info("Pop-up detected: Refresh Confirmation. Clicking Confirm.")
                self.appear_then_click(self.I_FRESH_ENSURE, interval=1.5)
                continue
            # 检查票数，同时确认奖励已领取且已返回突破列表。
            if not self.check_ticket(con.raid_config.number_base):
                break
            # 仅胜利场次计入上限，通用战斗的 current_count 仍用于战前配置。
            if successful_count >= con.raid_config.number_attack:
                logger.info(f'Successful count {successful_count}, max count {con.raid_config.number_attack}')
                break
            # ----------------------------------------开始进攻
            medal, index = self.find_one(False)
            if not medal and not index:
                # 已经没有可以挑战的了，只能刷新
                if con.raid_config.when_attack_fail == WhenAttackFail.CONTINUE:
                    logger.info('No one can attack and then refresh')
                    if self.check_refresh():
                        continue
                    else:
                        success = False
                        break
                else:
                    logger.info('No one can attack, break')
                    # 检查是否有“刷新确认”弹窗挡路
                    if self.appear(self.I_FRESH_ENSURE):
                        logger.info("Closing obstructing refresh dialog (Click Ensure)...")
                        # 点击“确定”来完成刷新（或者你可以改成点取消）
                        self.appear_then_click(self.I_FRESH_ENSURE, interval=2)
                    success = False
                    break
            # 判断是不是左上角第一个
            lock_before = con.general_battle_config.lock_team_enable
            if index == 1:
                logger.info('Now is the first one')
                if con.raid_config.exit_four:
                    logger.info('Exit four enable')
                    self.fire(index)
                    self.run_general_battle_back(con.general_battle_config, exit_four=True)
                    self.fire(index)
                    self.run_general_battle_back(con.general_battle_config, exit_four=True)
                    self.fire(index)
                    self.run_general_battle_back(con.general_battle_config, exit_four=True)
                    self.fire(index)
                    self.run_general_battle_back(con.general_battle_config, exit_four=True)
            elif self.check_medal_is_frog(frog, medal, index):
                # 如果挑战的这只是呱太的话，就要把锁定改为不锁定
                con.general_battle_config.lock_team_enable = False
            self.fire(index)
            last_battle = self.run_general_battle(con.general_battle_config)
            if last_battle:
                successful_count += 1
                logger.info(f'Successful raids: {successful_count}/{con.raid_config.number_attack}')
            if lock_before:
                con.general_battle_config.lock_team_enable = lock_before
            # 检查是否每三次领一个奖励
            if self.reward_detect_click(False):
                logger.info('Rewards of three wins')
                continue
            # 战斗返回时可能还在过渡画面，先有限重试确认页面，再判断刷新或退出。
            if not self.is_realm_raid_page() and not self.check_ticket(con.raid_config.number_base):
                break
            # 刷新 >> 如果勾选了三次刷新并且到达了三次，就刷新
            if con.raid_config.three_refresh and self.appear(self.I_RR_THREE, threshold=0.8):
                logger.info('Three refresh')
                if self.check_refresh():
                    continue
                else:
                    success = False
                    break
            # 刷新 >> 如果上一轮的失败并且勾选了失败刷新，就刷新
            if not last_battle and con.raid_config.when_attack_fail == WhenAttackFail.REFRESH:
                logger.info('Battle lost and then refresh')
                if self.check_refresh():
                    continue
                else:
                    success = False
                    break
            # 如果上一轮失败 -> 退出
            if not last_battle and con.raid_config.when_attack_fail == WhenAttackFail.EXIT:
                logger.info('Battle lost and exit')
                break


        self.ui_click(self.I_BACK_RED, self.I_CHECK_EXPLORATION)
        self.goto_page(page_main)
        self.set_next_run(task='RealmRaid', success=success, finish=True)
        raise TaskEnd








    # ----------------------------------------------------------------------------------------------------------------------
    # 2023.7.21 改版个人突破

    def ensure_lock(self, lock_team_enable: bool):
        """
        确保锁定阵容
        :param lock_team_enable:
        :return:
        """
        if lock_team_enable:
            while 1:
                self.screenshot()
                if self.appear_then_click(self.I_UNLOCK, interval=1):
                    continue
                if self.appear_then_click(self.I_UNLOCK_2, interval=1):
                    continue
                if self.appear(self.I_LOCK_2, threshold=0.9):
                    break
                if self.appear(self.I_LOCK, threshold=0.9):
                    break
            logger.info(f'Click {self.I_UNLOCK.name}')
        else:
            while 1:
                self.screenshot()
                if self.appear_then_click(self.I_LOCK, interval=1):
                    continue
                if self.appear_then_click(self.I_LOCK_2, interval=1):
                    continue
                if self.appear(self.I_UNLOCK_2, threshold=0.9):
                    break
                if self.appear(self.I_UNLOCK, threshold=0.9):
                    break
            logger.info(f'Click {self.I_LOCK.name}')

    def is_frog(self, screenshot: bool=True) -> bool:
        """
        判断是不是呱太活动
        :return:
        """
        if screenshot:
            self.screenshot()
        if self.appear(self.I_FROG_MEDAL):
            return True
        return False

    def check_ticket(self, base: int=0) -> bool:
        """
        检查是不是有票， 检查这个票是否大于等于基准
        :param base:
        :return:
        """
        if base < 0 or base > 30:
            logger.warning(f'It is not a valid base {base}')
            base = 0
        # 初次识别失败后，每隔一秒重新截图，最多重试十次。
        for retry in range(self.TICKET_OCR_RETRIES + 1):
            if retry:
                time.sleep(1)
            self.screenshot()
            if self.reward_detect_click(False):
                logger.info('Claim raid reward before reading tickets')
            elif self.is_realm_raid_page():
                cu, res, total = self.O_NUMBER.ocr(self.device.image)
                # DigitCounter 识别失败会返回 (0, 0, 0)，不能当作没票。
                if total == 30 and 0 <= cu <= total and cu + res == total:
                    if cu == 0:
                        logger.warning('Execute raid failed, no ticket')
                        return False
                    if cu < base:
                        logger.warning('Execute raid failed, ticket is not enough')
                        return False
                    return True
                logger.warning(f'Invalid raid ticket OCR: {(cu, res, total)}')
            else:
                logger.warning('Not on the realm raid page; cannot read tickets')
            logger.warning(f'Raid ticket recognition failed (retry {retry}/{self.TICKET_OCR_RETRIES})')

        logger.error('Raid ticket recognition exhausted; saving screenshot to log/screenshots')
        try:
            self.device.save_screenshot(genre='realm_raid_ticket_ocr', interval=0)
        except Exception:
            logger.exception('Failed to save raid ticket screenshot')
        raise GameOcrError(f'Realm raid ticket OCR failed after {self.TICKET_OCR_RETRIES} retries')

    def is_realm_raid_page(self) -> bool:
        return (not self.is_in_real_battle(False)
                and self.appear(self.I_CHECK_REALM_RAID)
                and self.appear(self.I_BACK_RED))

    @cached_property
    def order_medal(self) -> ImageGrid:
        order_attack = self.config.realm_raid.raid_config.order_attack
        support_number = [0, 1, 2, 3, 4, 5]
        match = {
            0: self.I_MEDAL_0,
            1: self.I_MEDAL_1,
            2: self.I_MEDAL_2,
            3: self.I_MEDAL_3,
            4: self.I_MEDAL_4,
            5: self.I_MEDAL_5,
        }
        order = order_attack.replace(' ', '').replace('\n', '')
        order = re.split(r'>', order)
        order = [int(i) for i in order]
        order = [i for i in order if i in support_number]

        images = []
        for i in order:
            images.append(match[i])
        return ImageGrid(images)

    @cached_property
    def partition(self) -> list[RuleClick]:
        return [self.C_PARTITION_1, self.C_PARTITION_2, self.C_PARTITION_3, self.C_PARTITION_4, self.C_PARTITION_5,
                self.C_PARTITION_6, self.C_PARTITION_7, self.C_PARTITION_8, self.C_PARTITION_9]

    def find_one(self, screenshot: bool=True) -> tuple:
        """
        找到一个可以打的，并且检查一下是不是这一个的是第几个的
        我们约定次序是：从左到右 上到下
        1 2 3
        4 5 9
        7 8 9
        :return: 返回的第一个参数是一个RuleImage, 第二个参数是位置信息
        如果没有找到，返回None, None
        """
        if screenshot:
            self.screenshot()
        image = self.device.image
        # https://github.com/runhey/OnmyojiAutoScript/issues/71
        # 如果开始失败后继挑战剩下的
        if self.config.realm_raid.raid_config.when_attack_fail == WhenAttackFail.CONTINUE:
            for i, roi in enumerate(self.false_roi):
                self.false_image.roi_back = roi
                if not self.appear(self.false_image):
                    continue
                logger.info(f'Position {i+1} is a failed')
                x, y, w, h = self.partition[i].roi_back
                image[y:y+h, x:x+w, ...] = 0
        # -----------------------------------------------------
        target = self.order_medal.find_anyone(image)
        if target:
            center = target.front_center()
            for i, click in enumerate(self.partition):
                x1, x2, y1, y2 = click.roi_front[0], click.roi_front[0] + click.roi_front[2], \
                                 click.roi_front[1], click.roi_front[1] + click.roi_front[3]
                if x1 < center[0] < x2 and y1 < center[1] < y2:
                    logger.info(f'Find one medal [{target}], order is {i + 1}')
                    return target, i + 1

        return None, None

    def check_medal_is_frog(self, is_activity: False, target: RuleImage, order: int) -> bool:
        """
        检查这个是不是呱太，为此之前你还需要判断是不是 处于呱太活动的
        :param target:
        :param is_activity: 如果不是呱太活动，那么就不需要检查了
        :param order:
        :return:
        """
        if not is_activity:
            return False
        # 好像呱太的位置是只有 789这三个
        if order < 7:
            return False
        # 有时候四星可能和五星的混一起
        if target != self.I_MEDAL_5 and target != self.I_MEDAL_4:
            return False
        match_ocr = {
            1: self.O_FROG_1,
            2: self.O_FROG_2,
            3: self.O_FROG_3,
            4: self.O_FROG_4,
            5: self.O_FROG_5,
            6: self.O_FROG_6,
            7: self.O_FROG_7,
            8: self.O_FROG_8,
            9: self.O_FROG_9,
        }
        target_ocr = match_ocr[order]
        self.screenshot()
        if target_ocr.ocr(self.device.image) == 20:
            logger.info(f'Find frog medal [{target}]')
            return True
        return False

    def reward_detect_click(self, screenshot: bool=True) -> bool:
        """
        领取三胜奖励；票数和页面恢复由 check_ticket 有限重试。
        """
        if screenshot:
            self.screenshot()
        if self.is_in_real_battle(False):
            return False
        return self.appear_then_click(self.I_SOUL_RAID, interval=1.5)

    def check_refresh(self, screenshot: bool=True) -> bool:
        """
        检查是否出现了刷新的按钮
        如果可以刷新就刷新，返回True
        如果在CD中，就返回False
        :return:
        """
        if screenshot:
            self.screenshot()
        if not self.appear(self.I_FRESH):
            logger.info(f'No find refresh button and it is in CD')
            return False
        while 1:
            self.screenshot()
            if self.appear(self.I_FRESH_ENSURE):
                break
            if self.appear_then_click(self.I_FRESH, interval=1):
                continue
        while 1:
            self.screenshot()
            if not self.appear(self.I_FRESH_ENSURE):
                return True
            if self.appear_then_click(self.I_FRESH_ENSURE, interval=1):
                continue

    def fire(self, order: int):
        """
        挑战
        :param order:  第几个
        :return:
        """
        retry_clean = 0
        while not self.appear(self.I_RR_PERSON):
            if retry_clean > 20:
                logger.warning("Stuck too long, try force quit or random click")
            
            logger.info("Title not found! Checking for popups or rewards...")
            
            # 如果看到了“刷新确认”弹窗 (I_FRESH_ENSURE 是右边的确定)
            if self.appear(self.I_FRESH_ENSURE):
                logger.info("Refresh popup detected! Clicking CANCEL (Red Button).")
                # 点击“取消”按钮的坐标 (基于1280x720分辨率)
                self.device.click(x=530, y=460) 
                time.sleep(1.5)
                self.screenshot()
                continue

            # 点击屏幕正上方 (640, 50)，而不是右下角，避免误触"刷新"按钮
            logger.info("Clicking safe area to clear rewards...")
            self.device.click(x=640, y=50)  
            time.sleep(1.5)
            self.screenshot()
            retry_clean += 1
        
        click = self.partition[order - 1]
        
        # 进攻循环
        while 1:
            self.screenshot()
            
            # 双重保险：如果在进攻阶段又弹出了窗口，也把它关掉
            if self.appear(self.I_FRESH_ENSURE):
                logger.info("Refresh popup blocking attack! Clicking CANCEL.")
                self.device.click(x=530, y=460) # 点取消
                time.sleep(1.0)
                continue

            if not self.appear(self.I_RR_PERSON, threshold=0.8):
                break
            # https://github.com/runhey/OnmyojiAutoScript/issues/1692
            if self.appear_then_click(self.I_SOUL_RAID, interval=2):
                continue
            if self.appear_then_click(self.I_FIRE, interval=1):
                continue
            if self.click(click, interval=1.8):
                continue
                
        logger.info(f'Click fire {order} success')

    @cached_property
    def false_roi(self) -> list:
        width = 86
        height = 64
        x1 = 386
        x2 = 714
        x3 = 1047
        y1 = 143
        y2 = 277
        y3 = 414
        return [
            [x1, y1, width, height],  # 左上角
            [x2, y1, width, height],
            [x3, y1, width, height],
            [x1, y2, width, height],  # 左中
            [x2, y2, width, height],
            [x3, y2, width, height],
            [x1, y3, width, height],  # 左下
            [x2, y3, width, height],
            [x3, y3, width, height],
        ]

    @cached_property
    def false_image(self):
        return RuleImage(roi_front=(0 ,0, 63, 32),
                         roi_back=(0, 0, 100, 100),
                         threshold=0.8,
                         method="Template matching",
                         file="./tasks/RyouToppa/dev/loser_sign_1.png")

    @battle_wait_strategy()
    def battle_wait(self, *args, **kwargs):
        return self.battle_wait_with_strategy(*args, **kwargs)


if __name__ == "__main__":
    from module.config.config import Config
    from module.device.device import Device
    config = Config('oas1')
    device = Device(config)
    t = ScriptTask(config, device)

    t.run()

