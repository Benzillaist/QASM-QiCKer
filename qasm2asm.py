import numpy as np
from math import Floor
import qick
import re
from .asm_v1 import QickProgram, QickRegister

qreg = []
creg = []

instructions = []

# page = output channel
# page 0 = loops
# otherwise page = Floor(channel/2) + 1:
#   if channel%2 = 1:
#       21 = freq
#       22 = phase
#       23 = address = 0
#       24 = gain
#       25 = pulse details
#       26 = delay
#   else:
#       see below
# 11 = freq
# 12 = phase
# 13 = address = 0
# 14 = gain
# 15 = pulse details
# 16 = delay
#

class ASMRAveragerProgram(QickProgram):

    # def __init__(self, soccfg, cfg, qasm_file):
    #     self.cfg = cfg
    #     self.qasm_file = qasm_file
    #     return 0
    
    def __init__(self, soccfg, cfg):
        """
        Constructor for the AveragerProgram, calls make program at the end.
        For classes that inherit from this, if you want it to do something before the program is made and compiled:
        either do it before calling this __init__ or put it in the initialize method.
        """
        super().__init__(soccfg)
        self.cfg = cfg
        self.make_program()
        self.soft_avgs = 1
        if "soft_avgs" in cfg:
            self.soft_avgs = cfg['soft_avgs']
        if "rounds" in cfg:
            self.soft_avgs = cfg['rounds']
        # this is a 1-D loop
        self.loop_dims = [cfg['reps']]
        # average over the reps axis
        self.avg_level = 0
    
    # def get_mode_code(self, length, outsel=None, mode=None, phrst=None):
    #     if length >= 2**16 or length < 3:
    #         raise RuntimeError("Pulse length of %d is out of range (exceeds 16 bits, or less than 3) - use multiple pulses, or zero-pad the waveform" % (length))
    #     if outsel is None: outsel = "product"
    #     if mode is None: mode = "oneshot"
    #     if phrst is None: phrst = 0

    #     outsel_reg = {"product": 0, "dds": 1, "input": 2, "zero": 3}[outsel]
    #     mode_reg = {"oneshot": 0, "periodic": 1}[mode]
    #     mc = phrst*0b01000+mode_reg*0b00100+outsel_reg
    #     return mc << 16 | np.uint16(length)

    # def send_pulse(self, page, ch, freq, phase, address, gain, mode, delay):
    #     p = self
    #     p.regwi(page, 11, freq)
    #     p.regwi(page, 12, phase)
    #     p.regwi(page, 13, address)
    #     p.regwi(page, 14, gain)
    #     p.regwi(page, 15, mode)
    #     p.regwi(page, 16, delay)
    #     p.set(page, ch, 11, 12, 13, 14, 15, 16)

    def load_qasm(self, qasm_file):
        self.qasm_file = qasm_file
        with open(qasm_file, 'r') as f:
            cfg = self.cfg
            line = f.readline()
            try:
                while line:
                    print(line)
                    l_arr = line.split(' ')
                    match l_arr[0]:
                        case "qreg":
                            continue
                        case "creg":
                            continue
                        case "h":
                            ch = re.search("\[(.*?)\]", l_arr[1])
                            self.set_pulse_registers(ch=ch, style="arb", freq=cfg.qubit[ch].freq, phase=cfg.qubit[ch].phase, 
                                                     gain=cfg.qubit[ch].gain, length=(cfg.qubit[ch].length / 2), gen_ch=ch, waveform="qubit")
                            self.add_gauss(ch=ch, name="qubit", sigma=cfg.qubit[ch].sigma, length=(cfg.qubit[ch].length / 2))
                            # pg = Floor(int(ch)/2) + 1
                            # self.send_pulse(pg, ch, cfg.qubit[ch].freq, cfg.qubit[ch].phase, 0, cfg.qubit[ch].gain, self.get_mode_code(cfg.qubit[ch].length), 0)
                        case "x":
                            ch = re.search("\[(.*?)\]", l_arr[1])
                            self.set_pulse_registers(ch=ch, style="arb", freq=cfg.qubit[ch].freq, phase=cfg.qubit[ch].phase, 
                                                     gain=cfg.qubit[ch].gain, length=(cfg.qubit[ch].length), gen_ch=ch, waveform="qubit")
                            self.add_gauss(ch=ch, name="qubit", sigma=cfg.qubit[ch].sigma, length=(cfg.qubit[ch].length))
                        case _:
                            continue
                            raise Exception(f'QASM command not known/supported {l_arr[0]}')
                    line = f.readline()
            except:
                raise Exception(f'Something went wrong :(')
            
    # def init_registers(self):
    #     cfg = self.cfg
    #     for key in cfg.qubit:
    #         self.set_pulse_registers(ch = )

    def acquire(self, soc, threshold=None, angle=None, readouts_per_experiment=None, save_experiments=None, load_pulses=True, start_src="internal", progress=False):
        """
        This method optionally loads pulses on to the SoC, configures the ADC readouts, loads the machine code representation of the AveragerProgram onto the SoC, starts the program and streams the data into the Python, returning it as a set of numpy arrays.
        config requirements:
        "reps" = number of repetitions;

        :param soc: Qick object
        :type soc: Qick object
        :param threshold: threshold
        :type threshold: int
        :param angle: rotation angle
        :type angle: list
        :param readouts_per_experiment: readouts per experiment
        :type readouts_per_experiment: int
        :param save_experiments: saved readouts (by default, save all readouts)
        :type save_experiments: list
        :param load_pulses: If true, loads pulses into the tProc
        :type load_pulses: bool
        :param start_src: "internal" (tProc starts immediately) or "external" (each round waits for an external trigger)
        :type start_src: string
        :param progress: If true, displays progress bar
        :type progress: bool
        :returns:
            - expt_pts (:py:class:`list`) - list of experiment points
            - avg_di (:py:class:`list`) - list of lists of averaged accumulated I data for ADCs 0 and 1
            - avg_dq (:py:class:`list`) - list of lists of averaged accumulated Q data for ADCs 0 and 1
        """

        self.shot_angle = angle
        self.shot_threshold = threshold

        d_buf, avg_d, shots = super().acquire(soc, soft_avgs=self.soft_avgs, reads_per_rep=readouts_per_experiment, load_pulses=load_pulses, start_src=start_src, progress=progress)

        # reformat the data into separate I and Q arrays
        # save results to class in case you want to look at it later or for analysis
        self.di_buf = [d[:,0] for d in d_buf]
        self.dq_buf = [d[:,1] for d in d_buf]

        if threshold is not None:
            self.shots = shots

        n_ro = len(self.ro_chs)
        if save_experiments is None:
            avg_di = [d[:, 0] for d in avg_d]
            avg_dq = [d[:, 1] for d in avg_d]
        else:
            avg_di = [np.zeros(len(save_experiments)) for ro in self.ro_chs]
            avg_dq = [np.zeros(len(save_experiments)) for ro in self.ro_chs]
            for i_ch in range(n_ro):
                for nn, ii in enumerate(save_experiments):
                    avg_di[i_ch][nn] = avg_d[i_ch][ii, 0]
                    avg_dq[i_ch][nn] = avg_d[i_ch][ii, 1]

        return avg_di, avg_dq
    
    def make_program(self, qasm_file):
        """
        A template program which repeats the instructions defined in the body() method the number of times specified in self.cfg["reps"].
        """
        p = self

        rjj = 14
        rcount = 15
        p.regwi(0, rcount, 0)
        p.regwi(0, rjj, self.cfg['reps']-1)
        p.label("LOOP_J")

        p.load_qasm(qasm_file)

        p.mathi(0, rcount, rcount, "+", 1)

        p.memwi(0, rcount, self.counter_addr)

        p.loopnz(0, rjj, 'LOOP_J')

        p.end()