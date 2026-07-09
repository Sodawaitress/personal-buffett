interface AuthCardProps {
  children: React.ReactNode;
}

export function AuthCard({ children }: AuthCardProps) {
  return (
    <div className="min-h-screen bg-stone-50 flex items-center justify-center px-4">
      <div className="w-full max-w-sm bg-white border border-stone-200 rounded-lg p-8 shadow-sm">
        <div className="text-center mb-6">
          <h1 className="font-serif text-2xl text-stone-900">SirenBuffet</h1>
          <p className="text-xs text-stone-400 mt-0.5">私人芭菲特工</p>
        </div>
        {children}
      </div>
    </div>
  );
}
