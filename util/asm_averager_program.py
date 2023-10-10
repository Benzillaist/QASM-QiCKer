from typing import List, Union
import numpy as np
from qick import obtain
from .asm_v1 import QickProgram, QickRegister, QickRegisterManagerMixin

class ASMRAveragerProgram(QickProgram):
    """
    ASMRAveragerProgram class, do the same (or similar) experiment multiple .
    It is an abstract base class similar to the AveragerProgram, except has an outer loop which allows one to sweep a parameter in the real-time program rather than looping over it in software.  This can be more efficient for short duty cycles.
    Acquire gathers data from both ADCs 0 and 1.

    :param cfg: Configuration dictionary
    :type cfg: dict
    """

    def __init__(self, soccfg, cfg):
        """
        Constructor for the RAveragerProgram, calls make program at the end so for classes that inherit from this if you want it to do something before the program is made and compiled either do it before calling this __init__ or put it in the initialize method.
        """
        super().__init__(soccfg)
        self.cfg = cfg
        self.make_program()
        self.soft_avgs = 1
        if "rounds" in cfg:
            self.soft_avgs = cfg['rounds']
        # expts loop is the outer loop, reps loop is the inner loop
        self.loop_dims = [cfg['expts'], cfg['reps']]
        # average over the reps axis
        self.avg_level = 1

    def initialize(self):
        """
        Abstract method for initializing the program and can include any instructions that are executed once at the beginning of the program.
        """
        pass

    def body(self):
        """
        Abstract method for the body of the program
        """
        pass

    def update(self):
        """
        Abstract method for updating the program
        """
        pass

    def make_program(self):
        """
        A template program which repeats the instructions defined in the body() method the number of times specified in self.cfg["reps"].
        """
        p = self

        rcount = 13
        rii = 14
        rjj = 15

        p.initialize()

        p.regwi(0, rcount, 0)

        p.regwi(0, rii, self.cfg['expts']-1)
        p.label("LOOP_I")

        p.regwi(0, rjj, self.cfg['reps']-1)
        p.label("LOOP_J")

        p.body()

        p.mathi(0, rcount, rcount, "+", 1)

        p.memwi(0, rcount, self.counter_addr)

        p.loopnz(0, rjj, 'LOOP_J')

        p.update()

        p.loopnz(0, rii, "LOOP_I")

        p.end()

    def get_expt_pts(self):
        """
        Method for calculating experiment points (for x-axis of plots) based on the config.

        :return: Numpy array of experiment points
        :rtype: array
        """
        return self.cfg["start"]+np.arange(self.cfg["expts"])*self.cfg["step"]

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=None, save_experiments=None, start_src="internal", progress=False):
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

        expt_pts = self.get_expt_pts()

        n_ro = len(self.ro_chs)
        if save_experiments is None:
            avg_di = [d[..., 0] for d in avg_d]
            avg_dq = [d[..., 1] for d in avg_d]
        else:
            avg_di = [np.zeros((len(save_experiments), *d.shape[1:])) for d in avg_d]
            avg_dq = [np.zeros((len(save_experiments), *d.shape[1:])) for d in avg_d]
            for i_ch in range(n_ro):
                for nn, ii in enumerate(save_experiments):
                    avg_di[i_ch][nn] = avg_d[i_ch][ii, ..., 0]
                    avg_dq[i_ch][nn] = avg_d[i_ch][ii, ..., 1]

        return expt_pts, avg_di, avg_dq