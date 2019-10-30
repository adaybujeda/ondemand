%{!?ncpus: %define ncpus 12}
%global package_name ondemand
%{!?package_release: %define package_release 1}
%{!?git_tag: %define git_tag v%{package_version}}
%define git_tag_minus_v %(echo %{git_tag} | sed -r 's/^v//')
%define runtime_version %(echo %{git_tag_minus_v} | sed -r 's/^([0-9])\.([0-9]).*/\\1.\\2/g')
%define selinux_policy_ver %(rpm --qf "%%{version}-%%{release}" -q selinux-policy)
%global selinux_module_version %{package_version}.%{package_release}
%global gem_home %{scl_ondemand_gem_home}/ondemand/%{version}
%global gems_name ondemand-gems-%{version}

%define __brp_mangle_shebangs /bin/true

Name:      %{package_name}
Version:   %{package_version}
Release:   %{package_release}%{?dist}
Summary:   Web server that provides users access to HPC resources

Group:     System Environment/Daemons
License:   MIT
URL:       https://osc.github.io/Open-OnDemand
Source0:   https://github.com/OSC/%{package_name}/archive/%{git_tag}.tar.gz
Source1:   ondemand-selinux.te
Source2:   ondemand-selinux-systemd.te
Source3:   ondemand-selinux.fc

# Disable debuginfo as it causes issues with bundled gems that build libraries
%global debug_package %{nil}

# Avoid duplicate build-id files between builds of ondemand-gems
%global _build_id_links none

# Check if system uses systemd by default
%if 0%{?rhel} >= 7 || 0%{?fedora} >= 16
%bcond_without systemd
%else
%bcond_with systemd
%endif

%if 0%{?rhel} >= 8
%bcond_with scl_apache
%define apache_confd /etc/httpd/conf.d
%define apache_service httpd
%define htcacheclean_service htcacheclean
%else
%bcond_without scl_apache
%define apache_confd /opt/rh/httpd24/root/etc/httpd/conf.d
%define apache_service httpd24-httpd
%define htcacheclean_service httpd24-htcacheclean
%endif

# Work around issue with EL6 builds
# https://stackoverflow.com/a/48801417
%if 0%{?rhel} < 7
%define __strip /opt/rh/devtoolset-6/root/usr/bin/strip
%endif

# Disable automatic dependencies as it causes issues with bundled gems and
# node.js packages used in the apps
AutoReqProv:     no

BuildRequires:   ondemand-runtime = %{runtime_version}
BuildRequires:   ondemand-scldevel = %{runtime_version}
BuildRequires:   sqlite-devel, curl, make, zlib-devel, libxslt-devel
BuildRequires:   ondemand-ruby = %{runtime_version}
BuildRequires:   ondemand-python = %{runtime_version}
BuildRequires:   ondemand-nodejs = %{runtime_version}
BuildRequires:   rsync
BuildRequires:   git
Requires:        git
Requires:        sudo, lsof, sqlite-devel, cronie, wget, curl, make, rsync, file, libxml2, libxslt, zlib
Requires:        ondemand-apache = %{runtime_version}
Requires:        ondemand-nginx = 1.17.3
Requires:        ondemand-passenger = 6.0.4
Requires:        ondemand-ruby = %{runtime_version}
Requires:        ondemand-python = %{runtime_version}
Requires:        ondemand-nodejs = %{runtime_version}
Requires:        ondemand-runtime = %{runtime_version}
Requires:        %{gems_name}

%if %{with systemd}
BuildRequires: systemd
%{?systemd_requires}
%endif

%description
Open OnDemand is an open source release of OSC's OnDemand platform to provide
HPC access via a web browser, supporting web based file management, shell
access, job submission and interactive work on compute nodes.

%package -n %{name}-selinux
Summary: SELinux policy for OnDemand
BuildRequires:      selinux-policy, selinux-policy-devel, checkpolicy, policycoreutils
Requires:           %{name} = %{version}
Requires:           selinux-policy >= %{selinux_policy_ver}
Requires(post):     /usr/sbin/semodule, /sbin/restorecon, /usr/sbin/setsebool, /usr/sbin/selinuxenabled, /usr/sbin/semanage
Requires(post):     policycoreutils-python
Requires(post):     selinux-policy-targeted
Requires(postun):   /usr/sbin/semodule, /sbin/restorecon

%description -n %{name}-selinux
SELinux policy for OnDemand

%package -n %{gems_name}
Summary: Rubygems for OnDemand
AutoReqProv: no

%description -n %{gems_name}
Rubygem for OnDemand

%package -n ondemand-gems
Summary: Metapackage to include Rubygems for OnDemand
Requires: %{gems_name}

%description -n ondemand-gems
Metapackage to include Rubygems for OnDemand

%prep
%setup -q -n %{package_name}-%{git_tag_minus_v}


%build
%__mkdir selinux
pushd selinux
echo "SELinux policy %{selinux_policy_ver}"
%__cp %{SOURCE1} ./ondemand-selinux.te
%if 0%{?rhel} >= 7
%__cat %{SOURCE2} >> ./ondemand-selinux.te
%endif
%__cp %{SOURCE3} ./ondemand-selinux.fc
%__sed -i 's/@VERSION@/%{selinux_module_version}/' ./ondemand-selinux.te
%__make -f %{_datadir}/selinux/devel/Makefile
popd

scl enable ondemand - << \EOS
set -x
set -e
export GEM_HOME=$(pwd)/gems-build
export GEM_PATH=$(pwd)/gems-build:$GEM_PATH
rake --trace -mj%{ncpus} build
EOS


%install
%__install -p -m 644 -D selinux/%{name}-selinux.pp %{buildroot}%{_datadir}/selinux/packages/%{name}-selinux/%{name}-selinux.pp

scl enable ondemand - << \EOS
set -x
set -e
%__mkdir_p %{buildroot}%{gem_home}
%__mv ./gems-build/* %{buildroot}%{gem_home}/
export GEM_PATH=%{buildroot}%{gem_home}:$GEM_PATH
rake --trace install PREFIX=%{buildroot}/opt/ood

%__rm %{buildroot}/opt/ood/apps/*/log/production.log
echo "%{git_tag}" > %{buildroot}/opt/ood/VERSION
%__mkdir_p %{buildroot}%{_localstatedir}/www/ood/public
%__mkdir_p %{buildroot}%{_localstatedir}/www/ood/discover
%__mkdir_p %{buildroot}%{_localstatedir}/www/ood/register
%__mkdir_p %{buildroot}%{_localstatedir}/www/ood/apps/sys
%__mkdir_p %{buildroot}%{_localstatedir}/www/ood/apps/usr
%__mv %{buildroot}/opt/ood/apps/dashboard %{buildroot}%{_localstatedir}/www/ood/apps/sys/dashboard
%__mv %{buildroot}/opt/ood/apps/shell %{buildroot}%{_localstatedir}/www/ood/apps/sys/shell
%__mv %{buildroot}/opt/ood/apps/files %{buildroot}%{_localstatedir}/www/ood/apps/sys/files
# Work around issues where node modules go from a directory to symlink which breaks RPM updates
if [ -L %{buildroot}%{_localstatedir}/www/ood/apps/sys/files/node_modules/cloudcmd ]; then
    pushd %{buildroot}%{_localstatedir}/www/ood/apps/sys/files/node_modules
    dest=$(readlink %{buildroot}%{_localstatedir}/www/ood/apps/sys/files/node_modules/cloudcmd)
    unlink %{buildroot}%{_localstatedir}/www/ood/apps/sys/files/node_modules/cloudcmd
    cp -pr $dest %{buildroot}%{_localstatedir}/www/ood/apps/sys/files/node_modules/
    popd
fi
%__mv %{buildroot}/opt/ood/apps/file-editor %{buildroot}%{_localstatedir}/www/ood/apps/sys/file-editor
%__mv %{buildroot}/opt/ood/apps/activejobs %{buildroot}%{_localstatedir}/www/ood/apps/sys/activejobs
%__mv %{buildroot}/opt/ood/apps/myjobs %{buildroot}%{_localstatedir}/www/ood/apps/sys/myjobs
%__mv %{buildroot}/opt/ood/apps/bc_desktop %{buildroot}%{_localstatedir}/www/ood/apps/sys/bc_desktop
%__rm -rf %{buildroot}/opt/ood/apps
%__mkdir_p %{buildroot}%{_sharedstatedir}/ondemand-nginx/config/puns
%__mkdir_p %{buildroot}%{_sharedstatedir}/ondemand-nginx/config/apps/sys
%__mkdir_p %{buildroot}%{_sharedstatedir}/ondemand-nginx/config/apps/usr
%__mkdir_p %{buildroot}%{_sharedstatedir}/ondemand-nginx/config/apps/dev
%__mkdir_p %{buildroot}%{_tmppath}/ondemand-nginx

%__install -D -m 644 ood-portal-generator/share/ood_portal_example.yml \
    %{buildroot}%{_sysconfdir}/ood/config/ood_portal.yml
%__mkdir_p %{buildroot}%{apache_confd}
touch %{buildroot}%{apache_confd}/ood-portal.conf

%__install -D -m 644 nginx_stage/share/nginx_stage_example.yml \
    %{buildroot}%{_sysconfdir}/ood/config/nginx_stage.yml
touch %{buildroot}%{_sharedstatedir}/ondemand-nginx/config/apps/sys/dashboard.conf
touch %{buildroot}%{_sharedstatedir}/ondemand-nginx/config/apps/sys/shell.conf
touch %{buildroot}%{_sharedstatedir}/ondemand-nginx/config/apps/sys/files.conf
touch %{buildroot}%{_sharedstatedir}/ondemand-nginx/config/apps/sys/file-editor.conf
touch %{buildroot}%{_sharedstatedir}/ondemand-nginx/config/apps/sys/activejobs.conf
touch %{buildroot}%{_sharedstatedir}/ondemand-nginx/config/apps/sys/myjobs.conf

touch %{buildroot}%{_sysconfdir}/ood/config/ood_portal.sha256sum

%__mkdir_p %{buildroot}%{_sysconfdir}/sudoers.d
%__cat >> %{buildroot}%{_sysconfdir}/sudoers.d/ood << EOF
Defaults:apache !requiretty, !authenticate
Defaults:apache env_keep += "NGINX_STAGE_* OOD_*"
apache ALL=(ALL) NOPASSWD: /opt/ood/nginx_stage/sbin/nginx_stage
EOF
%__chmod 440 %{buildroot}%{_sysconfdir}/sudoers.d/ood

%__mkdir_p %{buildroot}%{_sysconfdir}/cron.d
%__cat >> %{buildroot}%{_sysconfdir}/cron.d/ood << EOF
#!/bin/bash
PATH=/sbin:/bin:/usr/sbin:/usr/bin
0 */2 * * * root [ -f /opt/ood/nginx_stage/sbin/nginx_stage ] && /opt/ood/nginx_stage/sbin/nginx_stage nginx_clean 2>&1 | logger -t nginx_clean
EOF

%__mkdir_p %{buildroot}%{_sysconfdir}/logrotate.d
%__cat >> %{buildroot}%{_sysconfdir}/logrotate.d/ood << EOF
%{_localstatedir}/log/ondemand-nginx/*/access.log %{_localstatedir}/log/ondemand-nginx/*/error.log {
  compress
  copytruncate
  missingok
  notifempty
}
EOF

%if %{with systemd}
%__mkdir_p %{buildroot}%{_sysconfdir}/systemd/system/%{apache_service}.service.d
%__cat >> %{buildroot}%{_sysconfdir}/systemd/system/%{apache_service}.service.d/ood.conf << EOF
[Service]
KillSignal=SIGTERM
KillMode=process
PrivateTmp=false
EOF
%__chmod 444 %{buildroot}%{_sysconfdir}/systemd/system/%{apache_service}.service.d/ood.conf
%endif
EOS

%post
%if %{with scl_apache}
%__sed -i 's/^HTTPD24_HTTPD_SCLS_ENABLED=.*/HTTPD24_HTTPD_SCLS_ENABLED="httpd24 %{?scl_ondemand_ruby}"/' \
    /opt/rh/httpd24/service-environment
%endif

%if %{with systemd}
/bin/systemctl daemon-reload &>/dev/null || :
%endif

# These NGINX app configs need to exist before rebuilding them
touch %{_sharedstatedir}/ondemand-nginx/config/apps/sys/dashboard.conf
touch %{_sharedstatedir}/ondemand-nginx/config/apps/sys/shell.conf
touch %{_sharedstatedir}/ondemand-nginx/config/apps/sys/files.conf
touch %{_sharedstatedir}/ondemand-nginx/config/apps/sys/file-editor.conf
touch %{_sharedstatedir}/ondemand-nginx/config/apps/sys/activejobs.conf
touch %{_sharedstatedir}/ondemand-nginx/config/apps/sys/myjobs.conf

# Migrate from OnDemand 1.3 or 1.4
if [ $1 -gt 1 ] && [ -d %{_sharedstatedir}/nginx/config ]; then
    echo "Making copy of %{_sharedstatedir}/nginx/config at %{_sharedstatedir}/nginx/config.rpmsave"
    cp -a %{_sharedstatedir}/nginx/config %{_sharedstatedir}/nginx/config.rpmsave
    find %{_sharedstatedir}/nginx/config/apps -type f -exec rm -f {} \;
    cat > /tmp/nginx_stage.yml <<EOF
pun_config_path: '/var/lib/nginx/config/puns/%%{user}.conf'
pun_pid_path: '/var/run/nginx/%%{user}/passenger.pid'
pun_socket_path: '/var/run/nginx/%%{user}/passenger.sock'
EOF
    echo "Kill all PUNs as part of upgrade."
    NGINX_STAGE_CONFIG_FILE=/tmp/nginx_stage.yml /opt/ood/nginx_stage/sbin/nginx_stage nginx_clean --force || :
    rm -f /tmp/nginx_stage.yml
    for d in `find %{_tmppath}/nginx -maxdepth 1 -mindepth 1 -type d 2>/dev/null` ; do
        new=$(echo $d | sed 's|%{_tmppath}/nginx|%{_tmppath}/ondemand-nginx|g')
        if [ -d $new ]; then
            continue
        fi
        cp -a $d $new
    done
    for d in `find %{_sharedstatedir}/nginx/tmp -maxdepth 1 -mindepth 1 -type d 2>/dev/null` ; do
        new=$(echo $d | sed 's|%{_sharedstatedir}/nginx/tmp|%{_tmppath}/ondemand-nginx|g')
        if [ -d $new ]; then
            continue
        fi
        cp -a $d $new
    done
    for d in `find %{_sharedstatedir}/nginx/config.rpmsave -type d 2>/dev/null`; do
        new=$(echo $d | sed 's|%{_sharedstatedir}/nginx/config.rpmsave|%{_sharedstatedir}/ondemand-nginx/config|g')
        if [ -d $new ]; then
            continue
        fi
        install -d $new
    done
    for f in `find %{_sharedstatedir}/nginx/config.rpmsave -type f 2>/dev/null`; do
        new=$(echo $f | sed 's|%{_sharedstatedir}/nginx/config.rpmsave|%{_sharedstatedir}/ondemand-nginx/config|g')
        if [ -f $new ]; then
            continue
        fi
        cp -a $f $new
    done
    for d in `find %{_localstatedir}/log/nginx -maxdepth 1 -mindepth 1 -type d 2>/dev/null`; do
        new=$(echo $d | sed 's|%{_localstatedir}/log/nginx|%{_localstatedir}/log/ondemand-nginx|g')
        if [ -d $new ]; then
            continue
        fi
        cp -a $d $new
    done
fi

%post selinux
SELINUX_TEMP=$(mktemp -t ondemand-selinux-enable.XXXXX)
echo "boolean -m --on httpd_can_network_connect" >> $SELINUX_TEMP
echo "boolean -m --on httpd_execmem" >> $SELINUX_TEMP
echo "boolean -m --on httpd_use_nfs" >> $SELINUX_TEMP
echo "boolean -m --on httpd_setrlimit" >> $SELINUX_TEMP
%if 0%{?rhel} >= 7
echo "boolean -m --on httpd_mod_auth_pam" >> $SELINUX_TEMP
%else
echo "boolean -m --on allow_httpd_mod_auth_pam" >> $SELINUX_TEMP
%endif
echo "boolean -m --on httpd_unified" >> $SELINUX_TEMP
echo "boolean -m --on httpd_run_stickshift" >> $SELINUX_TEMP
echo "boolean -m --on use_nfs_home_dirs" >> $SELINUX_TEMP
%if 0%{?rhel} >= 7
echo "boolean -m --on daemons_use_tty" >> $SELINUX_TEMP
%else
echo "boolean -m --on allow_daemons_use_tty" >> $SELINUX_TEMP
%endif
semanage -S targeted -i $SELINUX_TEMP
semodule -i %{_datadir}/selinux/packages/%{name}-selinux/%{name}-selinux.pp 2>/dev/null || :
restorecon -R %{_sharedstatedir}/ondemand-nginx
restorecon -R %{_localstatedir}/log/ondemand-nginx

%preun
if [ "$1" -eq 0 ]; then
%if %{with scl_apache}
%__sed -i 's/^HTTPD24_HTTPD_SCLS_ENABLED=.*/HTTPD24_HTTPD_SCLS_ENABLED="httpd24"/' \
    /opt/rh/httpd24/service-environment
%endif
/opt/ood/nginx_stage/sbin/nginx_stage nginx_clean --force &>/dev/null || :
fi

%preun selinux
semodule -r %{name}-selinux 2>/dev/null || :

%postun
if [ "$1" -eq 0 ]; then
%if %{with systemd}
/bin/systemctl daemon-reload &>/dev/null || :
/bin/systemctl try-restart %{apache_service}.service %{htcacheclean_service}.service &>/dev/null || :
%else
/sbin/service %{apache_service} condrestart &>/dev/null
/sbin/service %{htcacheclean_service} condrestart &>/dev/null
exit 0
%endif
fi

%postun selinux
if [ "$1" -ge "1" ] ; then # Upgrade
semodule -i %{_datadir}/selinux/packages/%{name}-selinux/%{name}-selinux.pp 2>/dev/null || :
fi

%posttrans
# Rebuild NGINX app configs and restart PUNs w/ no active connections
/opt/ood/nginx_stage/sbin/update_nginx_stage &>/dev/null || :
# Migrate from OnDemand 1.3 or 1.4
if [ -d %{_sharedstatedir}/nginx/config ] ; then
    rm -rf %{_sharedstatedir}/nginx/config
fi

# Restart apps in case PUN wasn't restarted
touch %{_localstatedir}/www/ood/apps/sys/dashboard/tmp/restart.txt
touch %{_localstatedir}/www/ood/apps/sys/shell/tmp/restart.txt
touch %{_localstatedir}/www/ood/apps/sys/files/tmp/restart.txt
touch %{_localstatedir}/www/ood/apps/sys/file-editor/tmp/restart.txt
touch %{_localstatedir}/www/ood/apps/sys/activejobs/tmp/restart.txt
touch %{_localstatedir}/www/ood/apps/sys/myjobs/tmp/restart.txt

# Rebuild Apache config and restart Apache httpd if config changed
/opt/ood/ood-portal-generator/sbin/update_ood_portal --rpm --detailed-exitcodes
if [[ $? -eq 3 ]] ; then
%if %{with systemd}
/bin/systemctl try-restart %{apache_service}.service %{htcacheclean_service}.service &>/dev/null || :
%else
/sbin/service %{apache_service} condrestart &>/dev/null
/sbin/service %{htcacheclean_service} condrestart &>/dev/null
exit 0
%endif
fi


%files
%defattr(-,root,root)

/opt/ood/VERSION
/opt/ood/mod_ood_proxy
/opt/ood/nginx_stage
/opt/ood/ood-portal-generator
/opt/ood/ood_auth_map
%{_localstatedir}/www/ood/apps/sys/dashboard
%{_localstatedir}/www/ood/apps/sys/shell
%{_localstatedir}/www/ood/apps/sys/files
%{_localstatedir}/www/ood/apps/sys/file-editor
%{_localstatedir}/www/ood/apps/sys/activejobs
%{_localstatedir}/www/ood/apps/sys/myjobs
%{_localstatedir}/www/ood/apps/sys/bc_desktop
%exclude %{_localstatedir}/www/ood/apps/sys/*/tmp/*

%dir %{_localstatedir}/www/ood
%dir %{_localstatedir}/www/ood/public
%dir %{_localstatedir}/www/ood/register
%dir %{_localstatedir}/www/ood/discover
%dir %{_localstatedir}/www/ood/apps
%dir %{_localstatedir}/www/ood/apps/sys
%dir %{_localstatedir}/www/ood/apps/usr

%dir %{_sysconfdir}/ood
%dir %{_sysconfdir}/ood/config
%config(noreplace,missingok) %{_sysconfdir}/ood/config/nginx_stage.yml
%config(noreplace,missingok) %{_sysconfdir}/ood/config/ood_portal.yml
%ghost %{_sysconfdir}/ood/config/ood_portal.sha256sum

%dir %{_sharedstatedir}/ondemand-nginx/config
%dir %{_sharedstatedir}/ondemand-nginx/config/puns
%dir %{_sharedstatedir}/ondemand-nginx/config/apps
%dir %{_sharedstatedir}/ondemand-nginx/config/apps/sys
%dir %{_sharedstatedir}/ondemand-nginx/config/apps/usr
%dir %{_sharedstatedir}/ondemand-nginx/config/apps/dev
%ghost %{_sharedstatedir}/ondemand-nginx/config/apps/sys/dashboard.conf
%ghost %{_sharedstatedir}/ondemand-nginx/config/apps/sys/shell.conf
%ghost %{_sharedstatedir}/ondemand-nginx/config/apps/sys/files.conf
%ghost %{_sharedstatedir}/ondemand-nginx/config/apps/sys/file-editor.conf
%ghost %{_sharedstatedir}/ondemand-nginx/config/apps/sys/activejobs.conf
%ghost %{_sharedstatedir}/ondemand-nginx/config/apps/sys/myjobs.conf
%dir %{_tmppath}/ondemand-nginx

%config(noreplace) %{_sysconfdir}/sudoers.d/ood
%config(noreplace) %{_sysconfdir}/cron.d/ood
%config(noreplace) %{_sysconfdir}/logrotate.d/ood
%ghost %{apache_confd}/ood-portal.conf
%if %{with systemd}
%config(noreplace) %{_sysconfdir}/systemd/system/%{apache_service}.service.d/ood.conf
%endif

%files -n %{gems_name}
%{gem_home}/*

%files -n ondemand-gems

%files -n %{name}-selinux
%{_datadir}/selinux/packages/%{name}-selinux/%{name}-selinux.pp

%changelog
* Fri Feb 08 2019 Morgan Rodgers <mrodgers@osc.edu> 1.5.4-2
- Second build for 1.5.4 (mrodgers@osc.edu)

* Fri Feb 08 2019 Morgan Rodgers <mrodgers@osc.edu> 1.5.4-1
- Bump release to 1.5.4 (mrodgers@osc.edu)

* Thu Feb 07 2019 Morgan Rodgers <mrodgers@osc.edu> 1.5.3-1
- Bump release to 1.5.3 (mrodgers@osc.edu)

* Tue Feb 05 2019 Trey Dockendorf <tdockendorf@osc.edu> 1.5.2-6
- Re-added rh-ruby24 back into apache startup (tdockendorf@osc.edu)

* Sun Feb 03 2019 Trey Dockendorf <tdockendorf@osc.edu> 1.5.2-5
- Fix Update to not copy config.rpmsave to config.rpmsave (tdockendorf@osc.edu)

* Sun Feb 03 2019 Trey Dockendorf <tdockendorf@osc.edu> 1.5.2-4
- Copy from config.rpmsave because earlier step removed app configs from
  original path (tdockendorf@osc.edu)

* Sat Feb 02 2019 Trey Dockendorf <tdockendorf@osc.edu> 1.5.2-3
- No longer set HTTPD24_HTTPD_SCLS_ENABLED, causes problems on RHEL 6 and not
  needed (tdockendorf@osc.edu)

* Fri Feb 01 2019 Trey Dockendorf <tdockendorf@osc.edu> 1.5.2-2
- Handle 1.3 to 1.5 upgrades and better upgrade handling Add /var/tmp/ondemand-
  nginx (tdockendorf@osc.edu)

* Fri Feb 01 2019 Trey Dockendorf <tdockendorf@osc.edu> 1.5.2-1
- Bump ondemand to 1.5.2 Improve 1.4 to 1.5 upgrade and don't suppress ood-
  portal-generator output during package installs (tdockendorf@osc.edu)

* Wed Jan 30 2019 Trey Dockendorf <tdockendorf@osc.edu> 1.5.1-1
- Update to 1.5.1 (tdockendorf@osc.edu)
- Prep for 1.5.0 build (tdockendorf@osc.edu)
- Remove ondemand-scl patch (tdockendorf@osc.edu)
- Have ondemand depend on ondemand meta packages and not direct SCLs
  (tdockendorf@osc.edu)
- Need pun_config_path too (tdockendorf@osc.edu)
- Only kill off old PUNs if upgrade and old PUN config directory still exists,
  hopefully once someone cleans up old config directory the upgrade steps will
  stop (tdockendorf@osc.edu)
- Add logic to kill of PUNs before upgrading so stray processes are not left
  behind (tdockendorf@osc.edu)
- Apply ondemand-scl patch (tdockendorf@osc.edu)
- Use /var/lib/ondemand-nginx and add logic to migrate /var/lib/nginx to
  /var/lib/ondemand-nginx (tdockendorf@osc.edu)
- Update ondemand package to support ondemand SCL (tdockendorf@osc.edu)

* Wed Jan 30 2019 Morgan Rodgers <mrodgers@osc.edu> 1.5.0-1
- Update OnDemand to version 1.5.0 (mrodgers@osc.edu)

* Fri Jan 11 2019 Morgan Rodgers <mrodgers@osc.edu> 1.4.10-1
- Update ood to v1.4.10 (mrodgers@osc.edu)

* Wed Jan 02 2019 Morgan Rodgers <mrodgers@osc.edu> 1.4.9-1
- Update OnDemand to v 1.4.9 (mrodgers@osc.edu)

* Mon Dec 31 2018 Morgan Rodgers <mrodgers@osc.edu> 1.4.8-1
- Update OnDemand to 1.4.8 (mrodgers@osc.edu)

* Thu Dec 27 2018 Trey Dockendorf <tdockendorf@osc.edu> 1.4.7-1
- Update OnDemand to 1.4.7 (tdockendorf@osc.edu)

* Fri Dec 21 2018 Morgan Rodgers <mrodgers@osc.edu> 1.4.6-3
- Revert ood_portal_generator version string (mrodgers@osc.edu)

* Thu Dec 20 2018 Trey Dockendorf <tdockendorf@osc.edu> 1.4.5-3
- Change cloudcmd symlink to directory during RPM build to avoid warnings
  during yum update (tdockendorf@osc.edu)

* Thu Dec 20 2018 Trey Dockendorf <tdockendorf@osc.edu> 1.4.5-2
- Fix so that cloudcmd node module directory is able to be replaced with a
  symlink (tdockendorf@osc.edu)
- Actually use package_version for version (tdockendorf@osc.edu)

* Wed Dec 19 2018 Morgan Rodgers <mrodgers@osc.edu> 1.4.5-1
- OnDemand 1.4.5 release (mrodgers@osc.edu)

* Tue Dec 04 2018 Trey Dockendorf <tdockendorf@osc.edu> 1.4.4-4
- Fix release (tdockendorf@osc.edu)

* Tue Dec 04 2018 Trey Dockendorf <tdockendorf@osc.edu> 1.4.4-3
- Fix dependency on nginx to use correct epoch number

* Tue Dec 04 2018 Morgan Rodgers <mrodgers@osc.edu> 1.4.4-2
- Ondemand 1.4.4 (mrodgers@osc.edu)

* Fri Oct 19 2018 Morgan Rodgers <mrodgers@osc.edu> 1.4.3-2
- Ondemand dependency update and switch to monorepo (mrodgers@osc.edu)

* Fri Sep 14 2018 Morgan Rodgers <mrodgers@osc.edu> 1.4.2-2
- Bump OOD version to v1.4.2 (mrodgers@osc.edu)

* Thu Sep 13 2018 Morgan Rodgers <mrodgers@osc.edu> 1.4.1-2
- Bump OOD version to 1.4.1 (mrodgers@osc.edu)
- Bump ondemand version to v1.4.0 (mrodgers@osc.edu)

* Wed Jul 18 2018 Trey Dockendorf <tdockendorf@osc.edu> 1.3.7-2
- Remove production.log (tdockendorf@osc.edu)

* Tue May 15 2018 Jeremy Nicklas <jnicklas@osc.edu> 1.3.7-1
- Bump ondemand to 1.3.7 (jnicklas@osc.edu)

* Mon Apr 30 2018 Jeremy Nicklas <jnicklas@osc.edu> 1.3.6-1
- Bump ondemand to 1.3.6 (jnicklas@osc.edu)

* Fri Apr 20 2018 Jeremy Nicklas <jnicklas@osc.edu> 1.3.5-2
- add version file for ondemand (jnicklas@osc.edu)

* Mon Apr 09 2018 Jeremy Nicklas <jnicklas@osc.edu> 1.3.5-1
- Bump ondemand to 1.3.5 (jnicklas@osc.edu)

* Fri Apr 06 2018 Jeremy Nicklas <jnicklas@osc.edu> 1.3.4-1
- Bump ondemand to 1.3.4 (jnicklas@osc.edu)

* Tue Mar 27 2018 Jeremy Nicklas <jnicklas@osc.edu> 1.3.3-1
- Bump ondemand to 1.3.3 (jnicklas@osc.edu)

* Mon Mar 26 2018 Jeremy Nicklas <jnicklas@osc.edu> 1.3.2-1
- Bump ondemand to 1.3.2 (jnicklas@osc.edu)
- set web server configs as ghost (jnicklas@osc.edu)
- Use macros where possible (tdockendorf@osc.edu)

* Wed Feb 28 2018 Trey Dockendorf <tdockendorf@osc.edu> 1.3.1-5
- Set modes to be more restrictive. Matches OSC puppet environment but still
  functions the same (tdockendorf@osc.edu)

* Wed Feb 28 2018 Trey Dockendorf <tdockendorf@osc.edu> 1.3.1-4
- Try to speed up builds by doing rake in parallel (tdockendorf@osc.edu)
- Set sudo config to noreplace (tdockendorf@osc.edu)

* Wed Feb 28 2018 Trey Dockendorf <tdockendorf@osc.edu> 1.3.1-3
- Move %%posttrans into %%post (#23) Run daemon-reload for systemd in %%post
  and %%postun (#22) Make systemd unit file override %%config(noreplace)
  (tdockendorf@osc.edu)

* Tue Feb 27 2018 Jeremy Nicklas <jnicklas@osc.edu> 1.3.1-2
- set apache config as ghost (jnicklas@osc.edu)

* Tue Feb 27 2018 Trey Dockendorf <tdockendorf@osc.edu> 1.3.1-1
- Bump ondemand to 1.3.1 (jnicklas@osc.edu)

* Wed Feb 14 2018 Trey Dockendorf <tdockendorf@osc.edu> 1.3.0-1
- update ondemand to v1.3.0 (jeremywnicklas@gmail.com)


