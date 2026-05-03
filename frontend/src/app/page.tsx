export default function DashboardPage() {
  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-slate-900 tracking-tight">Validation Dashboard</h1>
        <p className="text-slate-500 mt-2">Overview of OCR extraction performance and routing readiness.</p>
      </header>
      
      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { label: "Total Processed", value: "1,248" },
          { label: "Auto-Approved", value: "85%", highlight: "text-emerald-600" },
          { label: "Needs Review", value: "15%", highlight: "text-amber-600" },
          { label: "Avg. Score", value: "92.4" }
        ].map((kpi, i) => (
          <div key={i} className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
            <p className="text-sm font-medium text-slate-500 mb-1">{kpi.label}</p>
            <p className={`text-3xl font-bold ${kpi.highlight || "text-slate-900"}`}>{kpi.value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-8">
        {/* Recent Extractions Table */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
          <div className="p-5 border-b border-slate-100 flex justify-between items-center bg-slate-50">
            <h2 className="font-semibold text-slate-800">Recent Extractions</h2>
            <button className="text-sm text-indigo-600 hover:text-indigo-800 font-medium">View All</button>
          </div>
          <div className="p-0 overflow-x-auto">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead className="bg-slate-50 text-slate-500 border-b border-slate-200">
                <tr>
                  <th className="px-5 py-3 font-medium">ID</th>
                  <th className="px-5 py-3 font-medium">Provider</th>
                  <th className="px-5 py-3 font-medium">Score</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {[
                  { id: "#EXT-092", provider: "Mindee", score: "98.5%", status: "Approved" },
                  { id: "#EXT-091", provider: "Mock", score: "100%", status: "Approved" },
                  { id: "#EXT-090", provider: "Veryfi", score: "72.0%", status: "Review" },
                ].map((row, i) => (
                  <tr key={i} className="hover:bg-slate-50 transition-colors">
                    <td className="px-5 py-3 font-mono text-slate-500">{row.id}</td>
                    <td className="px-5 py-3">{row.provider}</td>
                    <td className="px-5 py-3 font-medium">{row.score}</td>
                    <td className="px-5 py-3">
                      <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${
                        row.status === 'Approved' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
                      }`}>
                        {row.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        
        {/* Delivery Candidates Queue */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
          <div className="p-5 border-b border-slate-100 flex justify-between items-center bg-slate-50">
            <h2 className="font-semibold text-slate-800">Ready for Routing</h2>
            <button className="text-sm text-indigo-600 hover:text-indigo-800 font-medium">Export</button>
          </div>
          <div className="p-5 space-y-4">
            {[
              { id: "DEL-101", customer: "Maria Silva", addr: "Rua A, 123 - Centro", value: "R$ 45,90" },
              { id: "DEL-102", customer: "João Souza", addr: "Av. Brasil, 400 - Sul", value: "R$ 120,00" },
            ].map((del, i) => (
              <div key={i} className="flex justify-between items-center p-3 hover:bg-slate-50 rounded-lg border border-slate-100 transition-colors">
                <div>
                  <p className="font-medium text-slate-800">{del.customer}</p>
                  <p className="text-xs text-slate-500 truncate max-w-xs">{del.addr}</p>
                </div>
                <div className="text-right">
                  <p className="font-semibold text-slate-900">{del.value}</p>
                  <p className="text-xs text-indigo-600 font-medium">{del.id}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
