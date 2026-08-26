import { redirect } from "next/navigation";

export default function RegisterPage() {
  redirect(`${process.env.NEXT_PUBLIC_APP_URL ?? "https://app.avenqo.ca"}/register`);
}
