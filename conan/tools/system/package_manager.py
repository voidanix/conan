import platform

from conans.client.graph.graph import CONTEXT_BUILD
from conans.errors import ConanException


class _SystemPackageManagerTool(object):
    mode_check = "check"
    mode_install = "install"
    tool_name = None
    install_command = ""
    update_command = ""
    check_command = ""

    def __init__(self, conanfile):
        self._conanfile = conanfile
        self._active_tool = self._conanfile.conf["tools.system.package_manager:tool"] or self.get_default_tool()
        self._sudo = True if self._conanfile.conf["tools.system.package_manager:sudo"] == "True" else False
        self._sudo_askpass = True if self._conanfile.conf["tools.system.package_manager:sudo_askpass"] == "True" else False
        self._mode = self._conanfile.conf["tools.system.package_manager:mode"] or self.mode_check
        self._arch = self._conanfile.settings_build.get_safe('arch') \
            if self._conanfile.context == CONTEXT_BUILD else self._conanfile.settings.get_safe('arch')
        self._arch_names = {}
        self._arch_separator = ""

    def get_default_tool(self):
        os_name = platform.system()
        if os_name in ["Linux", "FreeBSD"]:
            import distro
            os_name = distro.id() or os_name
        elif os_name == "Windows" and self._conanfile.conf["tools.microsoft.bash:subsystem"] == "msys2":
            os_name = "msys2"
        manager_mapping = {"apt-get": ["Linux", "ubuntu", "debian"],
                           "yum": ["pidora", "scientific", "xenserver", "amazon", "oracle", "amzn",
                                   "almalinux"],
                           "dnf": ["fedora", "rhel", "centos", "mageia"],
                           "brew": ["Darwin"],
                           "pacman": ["arch", "manjaro", "msys2"],
                           "choco": ["Windows"],
                           "zypper": ["opensuse", "sles"],
                           "pkg": ["freebsd"],
                           "pkgutil": ["Solaris"]}
        for tool, distros in manager_mapping.items():
            if os_name in distros:
                return tool

    def get_package_name(self, package):
        # TODO: should we only add the arch if cross-building?
        if self._arch in self._arch_names:
            return "{}{}{}".format(package, self._arch_separator,
                                   self._arch_names.get(self._arch))
        return package

    @property
    def sudo_str(self):
        sudo = "sudo " if self._sudo else ""
        askpass = "-A " if self._sudo and self._sudo_askpass else ""
        return "{}{}".format(sudo, askpass)

    def run(self, method, *args, **kwargs):
        if self._active_tool == self.__class__.tool_name:
            return method(*args, **kwargs)

    def install(self, *args, **kwargs):
        return self.run(self._install, *args, **kwargs)

    def update(self, *args, **kwargs):
        return self.run(self._update, *args, **kwargs)

    def check(self, *args, **kwargs):
        return self.run(self._check, *args, **kwargs)

    def _install(self, packages, update=False, check=True, **kwargs):
        if update:
            self.update()

        if check:
            packages = self.check(packages)

        if self._mode == self.mode_check and packages:
            raise ConanException("System requirements: '{0}' are missing but can't install "
                                 "because tools.system.package_manager:mode is '{1}'."
                                 "Please update packages manually or set "
                                 "'tools.system.package_manager:mode' "
                                 "to '{2}' in the [conf] section of the profile, "
                                 "or in the command line using "
                                 "'-c tools.system.package_manager:mode={2}'".format(", ".join(packages),
                                                                                     self.mode_check,
                                                                                     self.mode_install))
        elif packages:
            packages_arch = [self.get_package_name(package) for package in packages]
            if packages_arch:
                command = self.install_command.format(sudo=self.sudo_str,
                                                      tool=self.tool_name,
                                                      packages=" ".join(packages_arch),
                                                      **kwargs)
                return self._conanfile.run(command)
        else:
            self._conanfile.output.info("System requirements: {} already "
                                        "installed".format(" ".join(packages)))

    def _update(self):
        if self._mode == self.mode_check:
            raise ConanException("Can't update because tools.system.package_manager:mode is '{0}'."
                                 "Please update packages manually or set "
                                 "'tools.system.package_manager:mode' "
                                 "to '{1}' in the [conf] section of the profile, "
                                 "or in the command line using "
                                 "'-c tools.system.package_manager:mode={1}'".format(self.mode_check,
                                                                                     self.mode_install))
        command = self.update_command.format(sudo=self.sudo_str, tool=self.tool_name)
        return self._conanfile.run(command)

    def _check(self, packages):
        missing = [pkg for pkg in packages if self.check_package(self.get_package_name(pkg)) != 0]
        return missing

    def check_package(self, package):
        command = self.check_command.format(tool=self.tool_name,
                                            package=package)
        return self._conanfile.run(command, ignore_errors=True)


class Apt(_SystemPackageManagerTool):
    # TODO: apt? apt-get?
    tool_name = "apt-get"
    install_command = "{sudo}{tool} install -y {recommends}{packages}"
    update_command = "{sudo}{tool} update"
    check_command = "dpkg-query -W -f='${{Status}}' {package} | grep -q \"ok installed\""

    def __init__(self, conanfile, arch_names=None):
        super(Apt, self).__init__(conanfile)
        self._arch_names = {"x86_64": "amd64",
                            "x86": "i386",
                            "ppc32": "powerpc",
                            "ppc64le": "ppc64el",
                            "armv7": "arm",
                            "armv7hf": "armhf",
                            "armv8": "arm64",
                            "s390x": "s390x"} if arch_names is None else arch_names

        self._arch_separator = ":"

    def install(self, packages, update=False, check=False, recommends=False):
        recommends_str = '' if recommends else '--no-install-recommends '
        return super(Apt, self).install(packages, update=update, check=check,
                                        recommends=recommends_str)


class Yum(_SystemPackageManagerTool):
    tool_name = "yum"
    install_command = "{sudo}{tool} install -y {packages}"
    update_command = "{sudo}{tool} check-update -y"
    check_command = "rpm -q {package}"

    def __init__(self, conanfile, arch_names=None):
        super(Yum, self).__init__(conanfile)
        self._arch_names = {"x86_64": "x86_64",
                            "x86": "i?86",
                            "ppc32": "powerpc",
                            "ppc64le": "ppc64le",
                            "armv7": "armv7",
                            "armv7hf": "armv7hl",
                            "armv8": "aarch64",
                            "s390x": "s390x"} if arch_names is None else arch_names
        self._arch_separator = "."


class Dnf(Yum):
    tool_name = "dnf"


class Brew(_SystemPackageManagerTool):
    tool_name = "brew"
    install_command = "{sudo}{tool} install {packages}"
    update_command = "{sudo}{tool} update"
    check_command = 'test -n "$({tool} ls --versions {package})"'


class Pkg(_SystemPackageManagerTool):
    tool_name = "pkg"
    install_command = "{sudo}{tool} install -y {packages}"
    update_command = "{sudo}{tool} update"
    check_command = "{tool} info {package}"


class PkgUtil(_SystemPackageManagerTool):
    tool_name = "pkgutil"
    install_command = "{sudo}{tool} --install --yes {packages}"
    update_command = "{sudo}{tool} --catalog"
    check_command = 'test -n "`{tool} --list {package}`"'


class Chocolatey(_SystemPackageManagerTool):
    tool_name = "choco"
    install_command = "{tool} --install --yes {packages}"
    update_command = "{tool} outdated"
    check_command = '{tool} search --local-only --exact {package} | ' \
                    'findstr /c:"1 packages installed."'


class PacMan(_SystemPackageManagerTool):
    tool_name = "pacman"
    install_command = "{sudo}{tool} -S --noconfirm {packages}"
    update_command = "{sudo}{tool} -Syyu --noconfirm"
    check_command = "{tool} -Qi {package}"

    def __init__(self, conanfile, arch_names=None):
        super(PacMan, self).__init__(conanfile)
        self._arch_names = {"x86": "lib32"} if arch_names is None else arch_names
        self._arch_separator = "-"


class Zypper(_SystemPackageManagerTool):
    tool_name = "zypper"
    install_command = "{sudo}{tool} --non-interactive in {packages}"
    update_command = "{sudo}{tool} --non-interactive ref"
    check_command = "rpm -q {package}"
