#!/usr/bin/python

__author__ = 'mmin18'
__version__ = '1.50803'

from subprocess import Popen, PIPE, check_call
from distutils.version import LooseVersion
import argparse
import sys
import os
import re
import time

def is_gradle_project(dir):
    return os.path.isfile(os.path.join(dir, 'build.gradle'))

def parse_properties(path):
    return os.path.isfile(path) and dict(line.strip().split('=') for line in open(path) if ('=' in line and not line.startswith('#'))) or {}

def balanced_braces(arg):
    if '{' not in arg:
        return ''
    chars = []
    n = 0
    for c in arg:
        if c == '{':
            if n > 0:
                chars.append(c)
            n += 1
        elif c == '}':
            n -= 1
            if n > 0:
                chars.append(c)
            elif n == 0:
                return ''.join(chars).lstrip().rstrip()
        elif n > 0:
            chars.append(c)
    return ''

def remove_comments(str):
    # remove comments in groovy
    return re.sub(r'''(/\*([^*]|[\r\n]|(\*+([^*/]|[\r\n])))*\*+/)|(//.*)''', '', str)

def __deps_list_eclipse(list, project):
    prop = parse_properties(os.path.join(project, 'project.properties'))
    for i in range(1,100):
        dep = prop.get('android.library.reference.%d' % i)
        if dep:
            absdep = os.path.abspath(os.path.join(project, dep))
            __deps_list_eclipse(list, absdep)
            if not absdep in list:
                list.append(absdep)

def __deps_list_gradle(list, project):
    str = ''
    with open(os.path.join(project, 'build.gradle'), 'r') as f:
        str = f.read()
    str = remove_comments(str)
    ideps = []
    # for depends in re.findall(r'dependencies\s*\{.*?\}', str, re.DOTALL | re.MULTILINE):
    for m in re.finditer(r'dependencies\s*\{', str):
        depends = balanced_braces(str[m.start():])
        for proj in re.findall(r'''compile project\(.*['"]:(.+)['"].*\)''', depends):
            ideps.append(proj.replace(':', '/'))
    if len(ideps) == 0:
        return

    path = project
    for i in range(1, 3):
        path = os.path.abspath(os.path.join(path, os.path.pardir))
        b = True
        deps = []
        for idep in ideps:
            dep = os.path.join(path, idep)
            if not os.path.isdir(dep):
                b = False
                break
            deps.append(dep)
        if b:
            for dep in deps:
                __deps_list_gradle(list, dep)
                if not dep in list:
                    list.append(dep)
            break

def deps_list(dir):
    if is_gradle_project(dir):
        list = []
        __deps_list_gradle(list, dir)
        return list
    else:
        list = []
        __deps_list_eclipse(list, dir)
        return list

def manifestpath(dir):
    if os.path.isfile(os.path.join(dir, 'AndroidManifest.xml')):
        return os.path.join(dir, 'AndroidManifest.xml')
    if os.path.isfile(os.path.join(dir, 'src/main/AndroidManifest.xml')):
        return os.path.join(dir, 'src/main/AndroidManifest.xml')

def package_name(dir):
    path = manifestpath(dir)
    if path and os.path.isfile(path):
        with open(path, 'r') as manifestfile:
            data = manifestfile.read()
            return re.findall('package=\"([\w\d_\.]+)\"', data)[0]

def countResDir(dir):
    c = 0
    d = 0
    if os.path.isdir(dir):
        for subd in os.listdir(dir):
            if subd=='drawable' or subd.startswith('drawable-'):
                c+=1
                d+=1
            if subd=='layout' or subd.startswith('layout-'):
                c+=1
                d+=1
            if subd=='values' or subd.startswith('values-'):
                c+=1
                d+=1
            if subd=='anim' or subd.startswith('anim-'):
                c+=1
            if subd=='color' or subd.startswith('color-'):
                c+=1
            if subd=='menu' or subd.startswith('menu-'):
                c+=1
            if subd=='raw' or subd.startswith('raw-'):
                c+=1
            if subd=='xml' or subd.startswith('xml-'):
                c+=1
            if subd=='mipmap' or subd.startswith('mipmap-'):
                c+=1
            if subd=='animator' or subd.startswith('animator-'):
                c+=1
    if d==0:
        return 0
    return c

def resdir(dir):
    dir1 = os.path.join(dir, 'res')
    dir2 = os.path.join(dir, 'src/main/res')
    a = countResDir(dir1)
    b = countResDir(dir2)
    if a>0 or b>0:
        return a>b and dir1 or dir2

def is_launchable_project(dir):
    if is_gradle_project(dir):
        with open(os.path.join(dir, 'build.gradle'), 'r') as buildfile:
            data = buildfile.read()
            data = remove_comments(data)
            if re.findall(r'''apply\s+plugin:\s*['"]com.android.application['"]''', data, re.MULTILINE):
                return True
    elif os.path.isfile(os.path.join(dir, 'project.properties')):
        with open(os.path.join(dir, 'project.properties'), 'r') as propfile:
            data = propfile.read()
            if re.findall(r'''^\s*target\s*=.*$''', data, re.MULTILINE) and not re.findall(r'''^\s*android.library\s*=\s*true\s*$''', data, re.MULTILINE):
                return True
    return False

def __append_project(list, dir, depth):
    if package_name(dir):
        list.append(dir)
    elif depth > 0:
        for cname in os.listdir(dir):
            if cname=='build' or cname=='bin':
                continue
            cdir = os.path.join(dir, cname)
            if os.path.isdir(cdir):
                __append_project(list, cdir, depth-1)

def list_projects(dir):
    list = []
    if os.path.isfile(os.path.join(dir, 'settings.gradle')):
        with open(os.path.join(dir, 'settings.gradle'), 'r') as f:
            data = f.read()
            for line in re.findall(r'''include\s*(.+)''', data):
                for proj in re.findall(r'''[\s,]+['"](.*?)['"]''', ','+line):
                    dproj = (proj.startswith(':') and proj[1:] or proj).replace(':', '/')
                    cdir = os.path.join(dir, dproj)
                    if package_name(cdir):
                        list.append(cdir)
    else:
        __append_project(list, dir, 2)
    return list

def list_aar_projects(dir, deps):
    pnlist = [package_name(i) for i in deps]
    pnlist.append(package_name(dir))
    list1 = []
    if os.path.isdir(os.path.join(dir, 'build/intermediates/incremental/mergeResources')):
        for dirpath, dirnames, files in os.walk(os.path.join(dir, 'build/intermediates/incremental/mergeResources')):
            if '/androidTest/' in dirpath:
                continue
            for fn in files:
                if fn=='merger.xml':
                    with open(os.path.join(dirpath, fn), 'r') as f:
                        data = f.read()
                        for ppath in re.findall(r'''path="([^"]*?/res)"''', data):
                            if not ppath in list1:
                                list1.append(ppath)
    list2 = []
    for ppath in list1:
        parpath = os.path.abspath(os.path.join(ppath, os.pardir))
        pn = package_name(parpath)
        if pn and not pn in pnlist:
            list2.append(ppath)
    return list2

def cexec(args, failOnError = True):
    p = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    output, err = p.communicate()
    if failOnError and p.returncode != 0:
        print('Fail to exec %s'%args)
        print(output)
        print(err)
        exit(1)
    return output

def get_android_jar(path):
    if not os.path.isdir(path):
        return None
    platforms = os.path.join(path, 'platforms')
    if not os.path.isdir(platforms):
        return None
    api = 0
    result = None
    for pd in os.listdir(platforms):
        pd = os.path.join(platforms, pd)
        if os.path.isdir(pd) and os.path.isfile(os.path.join(pd, 'source.properties')) and os.path.isfile(os.path.join(pd, 'android.jar')):
            with open(os.path.join(pd, 'source.properties'), 'r') as f:
                s = f.read()
                m = re.search(r'^AndroidVersion.ApiLevel\s*[=:]\s*(.*)$', s, re.MULTILINE)
                if m:
                    a = int(m.group(1))
                    if a > api:
                        api = a
                        result = os.path.join(pd, 'android.jar')
    return result

def get_adb(path):
    if os.path.isdir(path) and os.path.isfile(os.path.join(path, 'platform-tools/adb')):
        return os.path.join(path, 'platform-tools/adb')

def get_aapt(path):
    if os.path.isdir(path) and os.path.isdir(os.path.join(path, 'build-tools')):
        btpath = os.path.join(path, 'build-tools')
        minv = LooseVersion('0')
        minp = None
        for pn in os.listdir(btpath):
            if os.path.isfile(os.path.join(btpath, pn, 'aapt')):
                if LooseVersion(pn) > minv:
                    minp = os.path.join(btpath, pn, 'aapt')
        return minp

def get_android_sdk(dir, condf = get_android_jar):
    if os.path.isfile(os.path.join(dir, 'local.properties')):
        with open(os.path.join(dir, 'local.properties'), 'r') as f:
            s = f.read()
            m = re.search(r'^sdk.dir\s*[=:]\s*(.*)$', s, re.MULTILINE)
            if m and os.path.isdir(m.group(1)) and condf(m.group(1)):
                return m.group(1)

    path = os.getenv('ANDROID_HOME')
    if path and os.path.isdir(path) and condf(path):
        return path

    path = os.getenv('ANDROID_SDK')
    if path and os.path.isdir(path) and condf(path):
        return path

    path = os.path.expanduser('~/Library/Android/sdk')
    if path and os.path.isdir(path) and condf(path):
        return path

    path = '/Applications/android-sdk-mac_86'
    if path and os.path.isdir(path) and condf(path):
        return path

    path = '/android-sdk-mac_86'
    if path and os.path.isdir(path) and condf(path):
        return path

if __name__ == "__main__":

    dir = '.'
    sdkdir = None

    starttime = time.time()

    if len(sys.argv) > 1:
        parser = argparse.ArgumentParser()
        parser.add_argument('--sdk', help='specify Android SDK path')
        parser.add_argument('project')
        args = parser.parse_args()
        if args.sdk:
            sdkdir = args.sdk
        if args.project:
            dir = args.project

    projlist = [i for i in list_projects(dir) if is_launchable_project(i)]

    if not projlist:
        print('no valid android project found in '+os.path.abspath(dir))
        exit(1)

    pnlist = [package_name(i) for i in projlist]
    portlist = [0 for i in pnlist]
    stlist = [-1 for i in pnlist]

    if not sdkdir:
        sdkdir = get_android_sdk(dir)
        if not sdkdir:
            print('android sdk not found, specify in local.properties or export ANDROID_HOME')
            exit(1)

    adbpath = get_adb(sdkdir)
    if not adbpath:
        print('adb not found in %s/platform-tools'%sdkdir)
        exit(1)
    for i in range(0, 10):
        cexec([adbpath, 'forward', 'tcp:%d'%(41128+i), 'tcp:%d'%(41128+i)])
        output = cexec(['curl', 'http://127.0.0.1:%d/packagename'%(41128+i)], failOnError = False).strip()
        if output and output in pnlist:
            ii=pnlist.index(output)
            output = cexec(['curl', 'http://127.0.0.1:%d/appstate'%(41128+i)], failOnError=False).strip()
            if output and int(output) > stlist[ii]:
                portlist[ii] = (41128+i)
                stlist[ii] = int(output)

    maxst = max(stlist)
    port=0
    if maxst == -1:
        print('package %s not found, make sure your project is properly setup and running'%(len(pnlist)==1 and pnlist[0] or pnlist))
    elif stlist.count(maxst) > 1:
        alist = [pnlist[i] for i in range(0, len(pnlist)) if stlist[i] >= 0]
        print('multiple packages %s running%s'%(alist, (maxst==2 and '.' or ', keep one of your application visible and cast again')))
    else:
        i = stlist.index(maxst)
        port = portlist[i]
        dir = projlist[i]
        packagename = pnlist[i]
    for i in range(0, 10):
        if (41128+i) != port:
            cexec([adbpath, 'forward', '--remove', 'tcp:%d'%(41128+i)], failOnError=False)
    if port==0:
        exit(1)

    is_gradle = is_gradle_project(dir)
    if is_gradle:
        print('cast %s:%d as gradle project'%(packagename, port))
    else:
        print('cast %s:%d as eclipse project'%(packagename, port))

    android_jar = get_android_jar(sdkdir)
    if not android_jar:
        print('android.jar not found !!!\nUse local.properties or set ANDROID_HOME env')

    bindir = os.path.join(dir, is_gradle and 'build/lcast' or 'bin/lcast')
    binresdir = os.path.join(bindir, 'res')
    if not os.path.exists(os.path.join(binresdir, 'values')):
        os.makedirs(os.path.join(binresdir, 'values'))

    cexec(['curl', '--silent', '--output', os.path.join(binresdir, 'values/ids.xml'), 'http://127.0.0.1:%d/ids.xml'%port])
    cexec(['curl', '--silent', '--output', os.path.join(binresdir, 'values/public.xml'), 'http://127.0.0.1:%d/public.xml'%port])

    aaptpath = get_aapt(sdkdir)
    if not aaptpath:
        print('aapt not found in %s/build-tools'%sdkdir)
        exit(1)
    aaptargs = [aaptpath, 'package', '-f', '--auto-add-overlay', '-F', os.path.join(bindir, 'res.zip')]
    deps = deps_list(dir)
    if is_gradle:
        for dep in list_aar_projects(dir, deps):
            aaptargs.append('-S')
            aaptargs.append(dep)
    for dep in deps:
        aaptargs.append('-S')
        aaptargs.append(resdir(dep))
    aaptargs.append('-S')
    aaptargs.append(resdir(dir))
    aaptargs.append('-S')
    aaptargs.append(binresdir)
    aaptargs.append('-M')
    aaptargs.append(manifestpath(dir))
    aaptargs.append('-I')
    aaptargs.append(android_jar)
    cexec(aaptargs)

    cexec(['curl', '--silent', '-T', os.path.join(bindir, 'res.zip'), 'http://127.0.0.1:%d/pushres'%port])
    cexec(['curl', '--silent', 'http://127.0.0.1:%d/lcast'%port])

    cexec([adbpath, 'forward', '--remove', 'tcp:%d'%port], failOnError=False)

    elapsetime = time.time() - starttime
    print('finished in %dms'%(elapsetime*1000))
