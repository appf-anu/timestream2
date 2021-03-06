# Copyright (c) 2018 Kevin Murray <kdmfoss@gmail.com>
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict
from os import path as op
from sys import stderr, stdout, stdin
import warnings
import csv
import re

from tqdm import tqdm

csv.register_dialect('tsv',
                     delimiter='\t',
                     doublequote=False,
                     escapechar='\\',
                     lineterminator='\n',
                     quotechar='"',
                     quoting=csv.QUOTE_NONNUMERIC)


class TSPipeline(object):
    def __init__(self, *args, reporter=None):
        self.n = 0
        self.steps = list(args)
        if reporter is None:
            reporter = ResultRecorder()
        self.report = reporter

    def add_step(self, step):
        if not hasattr(step, "process_file"):
            raise ValueError("step doesn't seem to be a pipeline step")
        self.steps.append(step)
        return self # so one can chain calls

    def process_file(self, file):
        # This should mirror PipelineStep, so an entire pipeline can function
        # as a pipeline step
        for step in self.steps:
            try:
                file = step.process_file(file)
            except Exception as exc:
                warnings.warn(f"pipeline failed at {step.__class__.__name__}: {str(exc)}")
                file.report["Errors"] = str(exc)
                return file
        return file

    def process(self, input_stream, ncpus=1, progress=True):
        from concurrent.futures import as_completed, ThreadPoolExecutor, ProcessPoolExecutor
        if ncpus > 1:
            executor = ProcessPoolExecutor(max_workers=ncpus)
        else:
            executor = ThreadPoolExecutor()
        with executor:
            for file in tqdm(executor.map(self.process_file, input_stream), unit=" files"):
                if file is None:
                    continue
                self.report.record(file.instant, **file.report)
                self.n += 1
                yield file


    def __call__(self, *args, **kwargs):
        yield from self.process(*args, **kwargs)

    def process_to(self, input_stream, output, ncpus=1):
        for done in self.process(input_stream, ncpus=ncpus):
            output.write(done)

    def write(self, file):
        # TODO needed so that pipelines can be used as files
        pass

    def read(self, file):
        # TODO needed so that pipelines can be used as files
        pass

    def finish(self):
        for step in self.steps:
            step.finish()


class ResultRecorder(object):

    def __init__(self):
        self.fields = []
        self.data = defaultdict(dict)

    def record(self, instant, **kwargs):
        for key, val in kwargs.items():
            if key not in self.fields:
                self.fields.append(key)
            self.data[repr(instant)].update(kwargs.copy())

    def save(self, outpath, delim="\t"):
        if len(self.data) < 1:
            # No data, don't make file
            return
        with open(outpath, "w") as fh:
            tsvw = csv.writer(fh, dialect='tsv')
            tsvw.writerow(["Instant"] + self.fields)
            for instant, record in sorted(self.data.items()):
                line = [instant, ]
                for field in self.fields:
                    val = record.get(field, None)
                    if val is None:
                        val="NA"
                    if isinstance(val, str):
                        val = re.sub(r"\s+", " ", val, re.IGNORECASE | re.MULTILINE)
                    line.append(val)
                tsvw.writerow(line)


##########################################################################################
#                                     Pipeline steps                                     #
##########################################################################################


class PipelineStep(object):
    """A generic base class for pipeline steps.

    All pipeline steps should implement a method called `process_file` that accepts one
    argument `file`, and returns either TimestreamFile or a subclass of it.
    """

    def process_file(self, file):
        return file

    def finish(self):
        pass


class ResultRecorderStep(PipelineStep):
    
    def __init__(self, output_file):
        self.n = 0
        self.output_file = output_file
        self.report = ResultRecorder()
        self.write_interval = 1000  # write results every write_interval images

    def process_file(self, file):
        self.report.record(file.instant, **file.report)
        self.n += 1
        if self.n % self.write_interval == 0:
            self.report.save(self.output_file)

    def finish(self):
        self.report.save(self.output_file)


class CopyStep(PipelineStep):
    """Does Nothing"""
    pass


class WriteFileStep(PipelineStep):
    """Write each file to output, without changing the file"""
    def __init__(self, output):
        self.output = output

    def process_file(self, file):
        self.output.write(file)
        return file


class FileStatsStep(PipelineStep):
    def process_file(self, file):
        file.report.update({"FileName": op.basename(file.filename),
                            "FileSize": len(file.content)})
        return file
