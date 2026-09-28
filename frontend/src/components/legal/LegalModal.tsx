"use client";

import React from "react";

interface LegalModalProps {
  type: "privacy" | "terms";
  isOpen: boolean;
  onClose: () => void;
}

export default function LegalModal({ type, isOpen, onClose }: LegalModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fadeIn">
      <div className="relative w-full max-w-2xl max-h-[85vh] p-6 bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <h2 className="text-xl font-bold text-white">
            {type === "privacy" ? "Privacy Policy & Responsible Use" : "Terms of Service"}
          </h2>
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-white rounded-lg transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto py-4 text-sm text-slate-300 space-y-4 pr-2">
          {type === "privacy" ? (
            <>
              <section>
                <h3 className="font-semibold text-white mb-1">1. Private-by-Default Architecture</h3>
                <p className="text-slate-400">
                  All documents, previews, and exports are stored privately under strict authorization controls.
                  Other users cannot access or view your files without your credentials.
                </p>
              </section>

              <section>
                <h3 className="font-semibold text-white mb-1">2. Responsible Use & Permission Notice</h3>
                <p className="text-slate-400">
                  You must only upload, edit, and export documents for which you have explicit legal authority or ownership.
                  Do not use this application to forge, misrepresent, or alter legal records, official certificates, or copyrighted works without authorization.
                </p>
              </section>

              <section>
                <h3 className="font-semibold text-white mb-1">3. Document Content Logging</h3>
                <p className="text-slate-400">
                  Our servers do not log or store the contents of your documents in operational log files.
                  OCR text recognition and replacement strings are processed in memory and database records without being exposed to system logs.
                </p>
              </section>

              <section>
                <h3 className="font-semibold text-white mb-1">4. Right to Deletion ("Delete Now")</h3>
                <p className="text-slate-400">
                  You have full control to immediately delete any document or your entire account at any time.
                  When you trigger deletion, the original uploaded file, generated preview images, database records, and temporary exports are permanently purged from server disks.
                </p>
              </section>
            </>
          ) : (
            <>
              <section>
                <h3 className="font-semibold text-white mb-1">1. Acceptance of Terms</h3>
                <p className="text-slate-400">
                  By accessing or using PDF Editor, you agree to comply with and be bound by these terms. If you do not agree, do not use the service.
                </p>
              </section>

              <section>
                <h3 className="font-semibold text-white mb-1">2. Permitted Use</h3>
                <p className="text-slate-400">
                  You are granted a limited license to upload and modify documents for legitimate personal or business purposes.
                  Reverse engineering, submitting malicious or decompression-bomb files, and automated scraping are strictly prohibited.
                </p>
              </section>

              <section>
                <h3 className="font-semibold text-white mb-1">3. Usage Quotas & Limits</h3>
                <p className="text-slate-400">
                  To protect service stability, accounts are subject to fair-use rate limits on document storage, export rendering, and OCR requests.
                </p>
              </section>

              <section>
                <h3 className="font-semibold text-white mb-1">4. Disclaimer of Warranty</h3>
                <p className="text-slate-400">
                  The service is provided "as is" without warranty of any kind. PDF Editor is not liable for data loss or formatting discrepancies resulting from editing or export conversions.
                </p>
              </section>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="pt-4 border-t border-slate-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
