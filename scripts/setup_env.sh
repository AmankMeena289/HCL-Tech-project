#!/usr/bin/env bash
# One-time setup (Linux / WSL, no admin rights needed):
# creates ~/hc-venv with PySpark + Delta + pytest and downloads Java 17 to ~/jdk17.
set -e
cd ~
rm -rf ~/hc-venv
python3 -m venv --without-pip ~/hc-venv
curl -sSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
~/hc-venv/bin/python /tmp/get-pip.py -q
~/hc-venv/bin/pip install -q "pyspark==3.5.3" "delta-spark==3.2.1" pytest pandas
if [ ! -d ~/jdk17 ]; then
  curl -sSL "https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jdk/hotspot/normal/eclipse" -o /tmp/jdk17.tar.gz
  mkdir -p ~/jdk17 && tar -xzf /tmp/jdk17.tar.gz -C ~/jdk17 --strip-components=1
fi
~/jdk17/bin/java -version
~/hc-venv/bin/python -c "import pyspark,delta;print('pyspark',pyspark.__version__)"
echo SETUP_DONE
