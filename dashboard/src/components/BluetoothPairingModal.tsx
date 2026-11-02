import { useState } from 'react';
import { Badge, Button, Field, Input, Modal } from './ui';
import {
  IconBluetooth,
  IconCheck,
  IconChip,
  IconEye,
  IconEyeOff,
  IconWifi,
} from './icons';
import { api } from '@/lib/api';
import { tap } from '@/lib/native';
import { useDeskmate } from '@/store/useDeskmate';

interface BluetoothPairingModalProps {
  open: boolean;
  onClose: () => void;
  defaultSsid?: string;
}

// Custom 128-bit UUIDs matching firmware ble_prov.cpp
const BLE_SERVICE_UUID = '4fafc201-1fb5-459e-8fcc-c5c9c331914b';
const BLE_CHAR_SSID_UUID = 'beb5483e-36e1-4688-b7f5-ea07361b26a8';
const BLE_CHAR_PASS_UUID = 'beb5483e-36e1-4688-b7f5-ea07361b26a9';
const BLE_CHAR_STATUS_UUID = 'beb5483e-36e1-4688-b7f5-ea07361b26aa';

type BleStep = 'idle' | 'scanning' | 'connected' | 'provisioning' | 'success' | 'error';

export function BluetoothPairingModal({
  open,
  onClose,
  defaultSsid = '',
}: BluetoothPairingModalProps) {
  const pushToast = useDeskmate((state) => state.pushToast);
  const reconnect = useDeskmate((state) => state.reconnect);

  const [step, setStep] = useState<BleStep>('idle');
  const [bleDevice, setBleDevice] = useState<any>(null);
  const [gattServer, setGattServer] = useState<any>(null);
  const [ssid, setSsid] = useState(defaultSsid);
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [hardwareIp, setHardwareIp] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  // Check if browser supports Web Bluetooth API
  const isBleSupported = typeof navigator !== 'undefined' && 'bluetooth' in navigator;

  const handleReset = () => {
    try {
      if (gattServer && gattServer.connected) {
        gattServer.disconnect();
      }
    } catch {
      /* ignore */
    }
    setStep('idle');
    setBleDevice(null);
    setGattServer(null);
    setErrorMsg('');
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  const handlePair = async () => {
    if (!isBleSupported) return;
    tap();
    setStep('scanning');
    setErrorMsg('');

    try {
      const nav = navigator as any;
      const device = await nav.bluetooth.requestDevice({
        filters: [{ namePrefix: 'DeskMate' }],
        optionalServices: [BLE_SERVICE_UUID],
      });

      setBleDevice(device);

      device.addEventListener('gattserverdisconnected', () => {
        setGattServer(null);
      });

      // Connect to GATT server
      const server = await device.gatt.connect();
      setGattServer(server);
      setStep('connected');

      pushToast({
        kind: 'success',
        title: 'Bluetooth Connected',
        body: `Paired with ${device.name || 'DeskMate'} over Bluetooth LE.`,
      });
    } catch (err: any) {
      console.warn('BLE error:', err);
      if (err.name === 'NotFoundError') {
        // User closed or cancelled the picker dialog
        setStep('idle');
      } else {
        setErrorMsg(err?.message || 'Bluetooth connection failed');
        setStep('error');
      }
    }
  };

  const handleSendWifi = async () => {
    if (!gattServer || !ssid.trim()) return;
    tap();
    setStep('provisioning');
    setErrorMsg('');

    try {
      const service = await gattServer.getPrimaryService(BLE_SERVICE_UUID);
      const charSsid = await service.getCharacteristic(BLE_CHAR_SSID_UUID);
      const charPass = await service.getCharacteristic(BLE_CHAR_PASS_UUID);
      const charStatus = await service.getCharacteristic(BLE_CHAR_STATUS_UUID);

      // Listen for notifications from the hardware
      await charStatus.startNotifications();
      charStatus.addEventListener('characteristicvaluechanged', (event: any) => {
        const val = new TextDecoder().decode(event.target.value);
        console.log('[ble] Hardware notification:', val);

        if (val.startsWith('CONNECTED:')) {
          const ip = val.split(':')[1] || 'Assigned';
          setHardwareIp(ip);
          setStep('success');
          reconnect();
          pushToast({
            kind: 'success',
            title: 'Hardware Online!',
            body: `DeskMate connected to Wi-Fi with IP ${ip}`,
          });
        } else if (val.startsWith('FAILED:')) {
          const reason = val.replace('FAILED:', '') || 'Authentication failed';
          setErrorMsg(`Hardware could not connect: ${reason}`);
          setStep('error');
        }
      });

      const encoder = new TextEncoder();
      // 1. Send SSID over Bluetooth
      await charSsid.writeValue(encoder.encode(ssid.trim()));
      // 2. Send Password over Bluetooth (this triggers the hardware connection)
      await charPass.writeValue(encoder.encode(password));

      // Also persist into MongoDB database so cloud dashboard stays synchronized
      void api.device.setWifi(ssid.trim(), password).catch(() => {});
    } catch (err: any) {
      console.error('BLE write failed:', err);
      setErrorMsg(err?.message || 'Could not transmit credentials over Bluetooth');
      setStep('error');
    }
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={
        <div className="flex items-center gap-2 text-ink-100">
          <span className="p-1.5 rounded-lg bg-blue-500/20 text-blue-400">
            <IconBluetooth className="size-4" />
          </span>
          <span>Bluetooth Wi-Fi Setup</span>
        </div>
      }
    >
      <div className="space-y-4">
        {/* Step Indicator Header */}
        <div className="flex items-center justify-between text-[11px] font-semibold text-ink-400 pb-2 border-b border-ink-800">
          <span className={step === 'idle' || step === 'scanning' ? 'text-accent font-bold' : ''}>
            1. Pair BLE
          </span>
          <span>→</span>
          <span className={step === 'connected' || step === 'provisioning' ? 'text-accent font-bold' : ''}>
            2. Send Wi-Fi
          </span>
          <span>→</span>
          <span className={step === 'success' ? 'text-accent font-bold' : ''}>
            3. Connected!
          </span>
        </div>

        {/* Browser Support Check */}
        {!isBleSupported && (
          <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs">
            <p className="font-bold">Web Bluetooth Not Supported in this Browser</p>
            <p className="text-[11px] text-ink-300 mt-1">
              Web Bluetooth works in <strong>Google Chrome</strong>, <strong>Microsoft Edge</strong>, or <strong>Chrome on Android</strong>.
              Please switch to Chrome, or enter your Wi-Fi credentials in the manual form on the Settings page.
            </p>
          </div>
        )}

        {/* STEP 1: Idle / Start Pairing */}
        {isBleSupported && (step === 'idle' || step === 'scanning') && (
          <div className="text-center py-4 space-y-4">
            <div className="size-16 rounded-2xl bg-blue-500/15 border border-blue-500/30 text-blue-400 flex items-center justify-center mx-auto shadow-[0_0_25px_rgba(59,130,246,0.25)]">
              <IconBluetooth className="size-8 animate-pulse" />
            </div>

            <div>
              <h4 className="text-base font-bold text-ink-100">
                Pair with DeskMate
              </h4>
              <p className="text-xs text-ink-400 mt-1 max-w-sm mx-auto leading-relaxed">
                Just like pairing a smartwatch, your browser communicates directly with the ESP32 hardware over
                Bluetooth Low Energy to hand off your Wi-Fi network.
              </p>
            </div>

            <div className="rounded-xl bg-ink-950 p-3 text-left text-xs text-ink-300 space-y-1.5 border border-ink-800">
              <p className="font-bold text-ink-200">Before pairing:</p>
              <p>• Make sure the ESP32-S3 is powered on via USB.</p>
              <p>• The hardware advertises as <span className="font-mono text-accent">DeskMate-01</span>.</p>
              <p>• Make sure Bluetooth is enabled on your computer or phone.</p>
            </div>

            <Button
              variant="primary"
              onClick={handlePair}
              disabled={step === 'scanning'}
              className="w-full py-2.5 font-bold flex items-center justify-center gap-2 cursor-pointer"
            >
              <IconBluetooth className="size-4" />
              <span>{step === 'scanning' ? 'Searching for DeskMate...' : 'Search & Connect Bluetooth'}</span>
            </Button>
          </div>
        )}

        {/* STEP 2: Connected / Enter Wi-Fi Credentials */}
        {step === 'connected' && (
          <div className="space-y-4 py-2">
            <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <IconChip className="size-4 text-blue-400" />
                <span className="font-bold text-ink-100">{bleDevice?.name || 'DeskMate-01'}</span>
              </div>
              <Badge tone="good">Bluetooth Paired</Badge>
            </div>

            <div className="space-y-3">
              <Field
                label="Wi-Fi SSID (Network Name)"
                hint="2.4 GHz network (ESP32-S3 does not support 5 GHz Wi-Fi)."
              >
                <Input
                  value={ssid}
                  onChange={(e) => setSsid(e.target.value)}
                  placeholder="e.g. MyHomeNetwork_2.4G"
                  autoFocus
                />
              </Field>

              <Field
                label="Wi-Fi Password"
                hint="Sent directly over Bluetooth into the hardware's secure flash memory."
              >
                <div className="relative">
                  <Input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter Wi-Fi password"
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-200"
                  >
                    {showPassword ? <IconEyeOff className="size-4" /> : <IconEye className="size-4" />}
                  </button>
                </div>
              </Field>
            </div>

            <div className="flex gap-2 pt-2">
              <Button variant="outline" onClick={handleReset} className="w-1/3">
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleSendWifi}
                disabled={!ssid.trim()}
                className="w-2/3 flex items-center justify-center gap-2 cursor-pointer font-bold"
              >
                <IconWifi className="size-4" />
                <span>Beam Wi-Fi to Device</span>
              </Button>
            </div>
          </div>
        )}

        {/* STEP 3: Provisioning in Progress */}
        {step === 'provisioning' && (
          <div className="text-center py-6 space-y-4">
            <div className="size-16 rounded-2xl bg-amber-500/15 border border-amber-500/30 text-amber-400 flex items-center justify-center mx-auto shadow-[0_0_20px_rgba(245,158,11,0.25)]">
              <IconWifi className="size-8 animate-pulse" />
            </div>

            <div>
              <h4 className="text-base font-bold text-ink-100">
                Beaming Wi-Fi to Hardware...
              </h4>
              <p className="text-xs text-ink-400 mt-1 max-w-sm mx-auto">
                Credentials sent over Bluetooth. The ESP32 is writing to internal flash and connecting to <span className="text-accent font-bold font-mono">"{ssid}"</span>.
              </p>
            </div>

            <div className="w-full bg-ink-950 rounded-full h-2 overflow-hidden border border-ink-800">
              <div className="bg-accent h-full w-2/3 animate-[pulse_1.5s_infinite]" />
            </div>
          </div>
        )}

        {/* STEP 4: Success! */}
        {step === 'success' && (
          <div className="text-center py-5 space-y-4">
            <div className="size-16 rounded-2xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 flex items-center justify-center mx-auto shadow-[0_0_25px_rgba(16,185,129,0.3)]">
              <IconCheck className="size-8" />
            </div>

            <div>
              <h4 className="text-lg font-black text-ink-100">
                Hardware Connected!
              </h4>
              <p className="text-xs text-ink-400 mt-1">
                Your ESP32-S3 has joined the Wi-Fi network and is now online.
              </p>
            </div>

            <dl className="rounded-xl bg-ink-950 p-3 text-xs space-y-2 border border-ink-800 text-left">
              <div className="flex justify-between items-center">
                <span className="text-ink-400">Network (SSID):</span>
                <span className="font-mono font-bold text-accent">{ssid}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-ink-400">Device IP Address:</span>
                <span className="font-mono font-bold text-emerald-400">{hardwareIp || 'Assigned via DHCP'}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-ink-400">Storage:</span>
                <span className="text-ink-300">Saved in Flash (NVS) + MongoDB</span>
              </div>
            </dl>

            <Button
              variant="primary"
              onClick={handleClose}
              className="w-full py-2.5 font-bold cursor-pointer"
            >
              Done (Return to Dashboard)
            </Button>
          </div>
        )}

        {/* ERROR STATE */}
        {step === 'error' && (
          <div className="text-center py-4 space-y-4">
            <div className="p-3 rounded-xl bg-danger/10 border border-danger/30 text-danger text-xs text-left">
              <p className="font-bold">Setup Error</p>
              <p className="text-[11px] text-ink-300 mt-1">{errorMsg || 'An unknown error occurred'}</p>
            </div>

            <div className="flex gap-2">
              <Button variant="outline" onClick={handleClose} className="w-1/2">
                Close
              </Button>
              <Button variant="primary" onClick={handleReset} className="w-1/2">
                Try Again
              </Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

