#!/usr/bin/env bash


sudo mkdir -p /opt/photo-browser
sudo rsync -a /home/jkstill/ai/photo-browser/ /opt/photo-browser/

sudo python3.12 -m venv /opt/photo-browser/.venv
sudo /opt/photo-browser/.venv/bin/pip install --upgrade pip
sudo /opt/photo-browser/.venv/bin/pip install /opt/photo-browser

sudo install -D -m 0644 /opt/photo-browser/deploy/photo-browser.service /etc/systemd/system/photo-browser.service
sudo install -D -m 0644 /opt/photo-browser/deploy/photo-browser.sysusers.conf /etc/sysusers.d/photo-browser.conf
sudo systemd-sysusers

sudo install -d -m 0750 -o root -g photo-browser /etc/photo-browser
sudo install -m 0640 -o root -g photo-browser /opt/photo-browser/deploy/photo-browser.env.example /etc/photo-browser/photo-browser.env
sudoedit /etc/photo-browser/photo-browser.env

sudo systemctl daemon-reload
sudo systemctl enable --now photo-browser.service

