import { RegisterForm } from "@/components/auth/RegisterForm";

export default function SignupPage() {
  return (
    <main className="ced-auth-shell flex items-center justify-center bg-[var(--ced-bg)]">
      <RegisterForm />
    </main>
  );
}
