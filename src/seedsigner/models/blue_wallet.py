from . import Wallet
from seedsigner.helpers import Buttons, B, CameraProcess, CameraPoll, QR
from seedsigner.helpers.bcur import (bcur_decode, cbor_decode, bc32decode,
    bc32encode, cbor_encode, bcur_encode)
from seedsigner.helpers.ur2.ur_decoder import URDecoder
from seedsigner.helpers.ur2.ur_encoder import UREncoder
from seedsigner.helpers.ur2.cbor_lite import CBOREncoder
from seedsigner.helpers.ur2.ur import UR
from seedsigner.views import View

# External Dependencies
from embit.bip39 import mnemonic_to_bytes
from embit.bip39 import mnemonic_from_bytes
from embit import bip39
from embit import script
from embit import bip32
from embit import psbt
from embit.networks import NETWORKS
from embit import ec
from io import BytesIO
from binascii import unhexlify, hexlify, a2b_base64, b2a_base64
import re

class BlueWallet(Wallet):

    def __init__(self, current_network = "main", qr_density = Wallet.QRMEDIUM, policy = "PKWSH") -> None:
        Wallet.__init__(self, current_network, qr_density, policy)

    def set_seed_phrase(self, seed_phrase, passphrase):
        Wallet.set_seed_phrase(self, seed_phrase, passphrase)
        self.ur_decoder = URDecoder()

    def get_name(self) -> str:
        return "Blue Wallet"

    def parse_psbt(self, raw_psbt) -> bool:
        try:
            base64_psbt = a2b_base64(raw_psbt)
            self.tx = psbt.PSBT.parse(base64_psbt)
            self._parse_psbt()
        except Exception:
            return False

        return True

    def sign_transaction(self) -> (str):

        # sign the transaction
        self.tx.sign_with(self.root)

        #added section to trim psbt
        trimmed_psbt = psbt.PSBT(self.tx.tx)
        sigsEnd = 0
        for i, inp in enumerate(self.tx.inputs):
            sigsEnd += len(list(inp.partial_sigs.keys()))
            trimmed_psbt.inputs[i].partial_sigs = inp.partial_sigs

        raw_trimmed_signed_psbt = trimmed_psbt.serialize()

        # convert to base64
        b64_psbt = b2a_base64(raw_trimmed_signed_psbt)
        # somehow b2a ends with \n...
        if b64_psbt[-1:] == b"\n":
            b64_psbt = b64_psbt[:-1]

        return b64_psbt.decode('utf-8')

    def scan_animated_qr_pbst(self, controller) -> str:
        self.controller = controller
        self.buttons = controller.buttons
        self.controller.menu_view.draw_modal(["Initializing Camera"]) # TODO: Move to Controller
        # initialize camera
        self.controller.to_camera_queue.put(["start"])
        # First get blocking, this way it's clear when the camera is ready for the end user
        self.controller.from_camera_queue.get()
        self.camera_loop_timer = CameraPoll(0.05, self.process_camera_data)

        input = self.buttons.wait_for([B.KEY_LEFT, B.KEY_RIGHT])
        if input in (B.KEY_LEFT, B.KEY_RIGHT):
            self.camera_loop_timer.stop()
            self.controller.to_camera_queue.put(["stop"])
            return "nodata"
        elif input == B.OVERRIDE:
            self.camera_loop_timer.stop()
            self.controller.to_camera_queue.put(["stop"])
            if self.qr_data[0] == "invalid":
                return "invalid"
            elif self.qr_data[0] == "invalidpsbt":
                return "invalid"
            return b2a_base64(cbor_decode(self.ur_decoder.result.cbor))

    def process_camera_data(self):
        try:
            data = self.controller.from_camera_queue.get(False)
        except:
            data = ["nodata"]

        if data[0] != "nodata":
            if self.qr_total_frames == 0:
                # get total frames if not set
                self.qr_total_frames = type(self).total_frames_parse(data[0])
                if self.qr_total_frames == -1:
                    # when invalid, trigger override to display error
                    self.qr_data = ["invalid"]
                    self.buttons.trigger_override() # something went wrong, invalid QR
                    return
                self.qr_data = ["empty"]

            # get data and percentage
            decoder_work_check = self.ur_decoder.receive_part(data[0])
            if decoder_work_check == False:
                self.qr_data = ["invalidpsbt"]
                self.buttons.trigger_override() # something went wrong, invalid QR
                return
            self.percentage_complete = self.ur_decoder.estimated_percent_complete()

            # checking if all frames has been captured, exit camera processing
            if self.capture_complete():
                self.buttons.trigger_override()

            # if all frames have not all been captured, display progress to screen/display
            if not self.capture_complete() and self.scan_display_working == 0:
                self.scan_display_working = 1
                View.draw.rectangle((0, 0, View.canvas_width, View.canvas_height), outline=0, fill=0)
                tw, th = View.draw.textsize("Collecting QR Codes:", font=View.IMPACT25)
                View.draw.text(((240 - tw) / 2, 15), "Collecting QR Codes:", fill=View.color, font=View.IMPACT25)
                tw, th = View.draw.textsize(str(round(self.percentage_complete * 100)) + "% Complete", font=View.IMPACT22)
                View.draw.text(((240 - tw) / 2, 125), str(round(self.percentage_complete * 100)) + "% Complete", fill=View.color, font=View.IMPACT22)
                View.DispShowImage()
                self.scan_display_working = 0

        elif self.scan_started_ind == 0:
            self.scan_started_ind = 1
            self.controller.menu_view.draw_modal(["Scan Animated QR"], "", "Right to Exit")

    def total_frames_parse(data) -> int:
        if re.search("^UR\:CRYPTO-PSBT\/(\d+)\-(\d+)\/", data, re.IGNORECASE) != None:
            return 10 # valid
        elif re.search("^UR\:CRYPTO-PSBT", data, re.IGNORECASE) != None:
            return 1 # valid but only 1 segment
        else:
            return -1 #invalid

    def capture_complete(self) -> bool:
        if self.ur_decoder.is_complete():
            return True
        else:
            return False

    def set_network(self, network) -> bool:
        if network == "main":
            self.current_network = "main"
            self.hardened_derivation = "m/48h/0h/0h/2h"
        elif network == "test":
            self.current_network = "test"
            self.hardened_derivation = "m/48h/1h/0h/2h"
        else:
            return False

        return True

    def make_xpub_qr_codes(self, data, callback = None) -> []:
        qr = QR()
        images = []
        images.append(qr.qrimage(data))
        return images

    def make_signing_qr_codes(self, data, callback = None) -> []:
        qr = QR()
        images = []
        cnt = 0

        cbor_encoder = CBOREncoder()
        cbor_encoder.encodeBytes(a2b_base64(data))

        qr_ur_bytes = UR("crypto-psbt", cbor_encoder.get_bytes())
        ur2_encode = UREncoder(qr_ur_bytes,self.qrsize,0)
        qr_cnt = ur2_encode.fountain_encoder.seq_len()
        
        while not ur2_encode.is_complete():

            part = ur2_encode.next_part().upper()
            images.append(qr.qrimage(part))
            print(part)
            cnt += 1

            if callback != None:
                callback((cnt * 100.0) / qr_cnt)

        return images

    def set_qr_density(self, density):
        self.cur_qr_density = density
        if density == Wallet.QRLOW:
            self.qrsize = 50
        elif density == Wallet.QRMEDIUM:
            self.qrsize = 70
        elif density == Wallet.QRHIGH:
            self.qrsize = 120

    ###
    ### Internal Wallet Transactions OVERRIDE
    ###

    def get_policy(self, scope, scriptpubkey, xpubs):
        """Parse scope and get policy"""
        # we don't know the policy yet, let's parse it
        script_type = scriptpubkey.script_type()
        # p2sh can be either legacy multisig, or nested segwit multisig
        # or nested segwit singlesig
        if script_type == "p2sh":
            if scope.witness_script is not None:
                script_type = "p2sh-p2wsh"
            elif scope.redeem_script is not None and scope.redeem_script.script_type() == "p2wpkh":
                script_type = "p2sh-p2wpkh"
        policy = { "type": script_type }
        # expected multisig
        if "p2wsh" in script_type and scope.witness_script is not None:
            m, n, pubkeys = super().parse_multisig(scope.witness_script)

            # check pubkeys are derived from cosigners
            policy.update({
                "m": m, "n": n
            })
        return policy