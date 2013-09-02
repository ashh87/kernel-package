#!/usr/bin/env python

# Copyright 2013 Igor Gnatenko
# Author(s): Igor Gnatenko <i.gnatenko.brain AT gmail DOT com>
#            Bjorn Esser <bjoern.esser AT gmail DOT com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
# See http://www.gnu.org/copyleft/gpl.html for the full text of the license.

import os
import sys
import ConfigParser
import argparse
import urlgrabber
import urlgrabber.progress
import git
import re
import sh

WORK_DIR = os.path.dirname(sys.argv[0])
repo = git.Repo(WORK_DIR)
assert repo.bare == False
repo.config_reader()

class Options():
  name = "kernel"
  sha = repo.head.commit.hexsha
  prefix = None
  format = "tar.gz"
  archive = "%s-%s.%s" % (name, sha, format)
  directory = "sources"
  ver = [None, None, None, None, None]
  released = False
  sources = ["config-arm64", "config-arm-generic", "config-armv7", "config-armv7-generic", \
             "config-armv7-lpae", "config-debug", "config-generic", "config-i686-PAE", \
             "config-nodebug", "config-powerpc32-generic", "config-powerpc32-smp", \
             "config-powerpc64", "config-powerpc64p7", "config-powerpc-generic", "config-s390x", \
             "config-x86-32-generic", "config-x86_64-generic", "config-x86-generic", \
             "cpupower.config", "cpupower.service", "Makefile", "Makefile.config", "Makefile.release", \
             "merge.pl", "mod-extra.list", "mod-extra.sh", "mod-sign.sh", "x509.genkey"]
  try:
    with open("%s/config-local" % directory, "r"):
      pass
  except IOError:
    sources.append("config-local")

class Parser(argparse.ArgumentParser):
  def error(self, message):
    sys.stderr.write("error: %s\n" % message)
    self.print_help()
    sys.exit(2)

def set_args(parser):
  parser.add_argument("--with-patches", dest="patches", action="store_true", \
                      help="enable patches from sources/ directory")

def archive(options):
  f = open("%s/%s" % (options.directory, options.archive), "w")
  repo.archive(f, prefix=options.prefix, format=options.format)
  f.close()

def download_file(file_name):
  pg = urlgrabber.progress.TextMeter()
  urlgrabber.urlgrab("http://pkgs.fedoraproject.org/cgit/kernel.git/plain/%s" % file_name, \
                     "sources/%s" % file_name, progress_obj=pg)

def download_sources(options):
  for source in options.sources:
    download_file(source)

def download_spec(options):
  download_file("%s.spec" % options.name)

def download_files(options):
  try:
    os.makedirs(options.directory)
  except OSError:
    pass
  download_sources(options)
  download_spec(options)

def parse_spec(options):
  lines = []
  filters = ["^[ ]*#", "^\n"]
  expressions = [re.compile(x) for x in filters]
  with open("%s/%s.spec" % (options.directory, options.name), "r") as f:
    lines = f.readlines()
  lines_parsed = [s for s in lines if not len(filter(lambda re: re.match(s), expressions))]
  lines = []
  i = 0
  while i < len(lines_parsed):
    if re.search("^%changelog", lines_parsed[i]):
      try:
        while True:
          del lines_parsed[i]
      except IndexError:
        pass
    elif re.search("^%global released_kernel [01]", lines_parsed[i]):
      lines_parsed[i] = re.sub(r"[01]", "1" if options.released else "0", lines_parsed[i])
      i += 1
    elif re.search("^%define base_sublevel [0-9]+", lines_parsed[i]):
      lines_parsed[i] = re.sub(r"[0-9]+", options.ver[1], lines_parsed[i])
      i += 1
    elif re.search("^%define stable_update [0-9]+", lines_parsed[i]):
      lines_parsed[i] = re.sub(r"[0-9]+", options.ver[2], lines_parsed[i])
      i += 1
    elif re.search("^%define rcrev [0-9]+", lines_parsed[i]):
      lines_parsed[i] = re.sub(r"[0-9]+", re.sub(r"[^0-9]", "", options.ver[3]) if not options.released \
                                          else "0", lines_parsed[i])
      i += 1
    elif re.search("^%define gitrev [0-9]+", lines_parsed[i]):
      lines_parsed[i] = re.sub(r"[0-9]+", "0", lines_parsed[i])
      i += 1
    elif re.search("^%define debugbuildsenabled [01]", lines_parsed[i]):
      lines_parsed[i] = re.sub(r"[01]", "1", lines_parsed[i])
      i += 1
    elif re.search("^%define rawhide_skip_docs [01]", lines_parsed[i]):
      lines_parsed[i] = re.sub(r"[01]", "0", lines_parsed[i])
      i += 1
    elif re.search("^Source0: ", lines_parsed[i]):
      lines_parsed[i] = re.sub(r" .*$", " %s" % options.archive, lines_parsed[i])
      i += 1
    elif re.search("^[ ]*(Patch[0-9]+:|Apply(Optional|)Patch) ", lines_parsed[i]):
      lines_parsed[i] = re.sub(r"^", "#", lines_parsed[i])
      i += 1
#    elif re.search("^Source[1-9][0-9]+: ", lines_parsed[i]):
#      flag = True
#      for config in options.sources:
#        if re.search("^Source[1-9][0-9]+: %s" % config, lines_parsed[i]):
#          flag = False
#          break
#      if flag:
#        del lines_parsed[i]
#      else:
#        i += 1
    else:
      i += 1
  f = open("%s/%s.spec" % (options.directory, options.name), "w")
  for line in lines_parsed:
    f.write(line)
  f.close()

def get_kernel_info(options):
  lines = []
  with open("Makefile", "r") as f:
    lines = [f.next() for x in xrange(5)]
  i = 0
  for line in lines:
    options.ver[i] = re.sub(r"^.* = (.*)\n$", r"\1", line)
    i += 1
  if "=" in options.ver[3]:
    options.ver[3] = None
    options.released = True
  else:
    options.released = False

def main():
  parser = Parser(description="Make RPM from upstream linux kernel easy")
#  set_args(parser)
  args = parser.parse_args()
  options = Options()
  get_kernel_info(options)
#  options.prefix = "linux-%s.%s/" % (options.ver[0], options.ver[1] if options.released else (int(options.ver[1]) - 1))
  options.prefix = "linux-%s.%s/" % (options.ver[0], options.ver[1])
  if options.released:
    print "Version: %s.%s.%s" % (options.ver[0], options.ver[1], options.ver[2])
  else:
    print "Version: %s.%s.%s%s" % (options.ver[0], options.ver[1], options.ver[2], options.ver[3])
  print "Codename: %s" % options.ver[4]
  download_files(options)
  parse_spec(options)
#  archive(options)
  sys.exit(0)

if __name__ == "__main__":
  main()
