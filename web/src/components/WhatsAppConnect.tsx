import React, { useState } from 'react';
import { MessageSquare, QrCode, CheckCircle, Smartphone, ExternalLink } from 'lucide-react';

export const WhatsAppConnect: React.FC = () => {
  const [instanceName] = useState('fastagent-primary');
  const [paired, setPaired] = useState(false);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white tracking-tight">Connect WhatsApp & Google</h2>
        <p className="text-sm text-slate-400">Link your WhatsApp number and Google Account (Gmail & Calendar) to activate chat mode.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* WhatsApp Pairing Card */}
        <div className="p-6 bg-slate-900/80 border border-slate-800 rounded-xl space-y-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-lg">
              <MessageSquare className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-white">WhatsApp Integration (Evolution Go)</h3>
              <p className="text-xs text-slate-400">Instance: {instanceName}</p>
            </div>
          </div>

          <div className="p-6 bg-slate-950 rounded-xl border border-slate-800 text-center space-y-3">
            {paired ? (
              <div className="py-4 space-y-2">
                <CheckCircle className="w-12 h-12 text-emerald-400 mx-auto" />
                <p className="text-emerald-300 font-semibold text-sm">WhatsApp Connected & Active</p>
                <p className="text-xs text-slate-500">Ready to receive and process messages.</p>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="w-40 h-40 bg-white p-2 rounded-lg mx-auto flex items-center justify-center shadow-inner">
                  {/* Simulated QR Code representation */}
                  <div className="w-full h-full border-2 border-dashed border-slate-400 rounded flex flex-col items-center justify-center text-slate-800">
                    <QrCode className="w-16 h-16 text-slate-800 mb-1" />
                    <span className="text-[10px] font-mono font-bold">SCAN IN WHATSAPP</span>
                  </div>
                </div>
                <button
                  onClick={() => setPaired(true)}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-lg shadow transition-all"
                >
                  Simulate QR Pairing
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Google OAuth Card */}
        <div className="p-6 bg-slate-900/80 border border-slate-800 rounded-xl space-y-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 rounded-lg">
              <Smartphone className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-white">Google Account (OAuth 2.0)</h3>
              <p className="text-xs text-slate-400">Narrow scopes: Gmail & Calendar</p>
            </div>
          </div>

          <div className="p-6 bg-slate-950 rounded-xl border border-slate-800 space-y-3">
            <p className="text-xs text-slate-300 leading-relaxed">
              FastAgent requests narrow OAuth 2.0 permissions to read and schedule calendar events and send draft confirmation emails. All tokens are encrypted at rest with AES-256-GCM.
            </p>

            <a
              href="/api/auth/google/url"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center gap-2 w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg shadow transition-all"
            >
              <ExternalLink className="w-4 h-4" />
              Authorize with Google
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};
