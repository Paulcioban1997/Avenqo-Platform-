import { LOCALES } from "../src/lib/i18n/locales";
import { AUTH_DICTIONARY, getAuthStrings, type AuthStrings } from "../src/lib/i18n/auth-dictionary";

const requiredKeys: (keyof AuthStrings)[] = [
  "backToHome",
  "workspace",
  "asideLoginTitle",
  "asideLoginDesc",
  "asideRegisterTitle",
  "asideRegisterDesc",
  "asideForgotTitle",
  "asideForgotDesc",
  "asideResetTitle",
  "asideResetDesc",
  "legal",
  "badgeLogin",
  "badgeRegister",
  "badgeForgot",
  "badgeReset",
  "headingLogin",
  "headingRegister",
  "headingForgot",
  "headingReset",
  "subheadingLogin",
  "subheadingRegister",
  "subheadingForgot",
  "subheadingReset",
  "firstName",
  "lastName",
  "organization",
  "billingEmail",
  "industry",
  "email",
  "emailAddress",
  "password",
  "newPassword",
  "confirmPassword",
  "passwordHint",
  "loginSubmit",
  "registerSubmit",
  "sendResetLink",
  "resetSubmit",
  "forgotPasswordLink",
  "forgotPasswordTitle",
  "backToLogin",
  "hasAccountPrompt",
  "newToAvenqoPrompt",
  "signInLink",
  "createOrgLink",
  "linkExpired",
  "linkInvalid",
  "missingToken",
  "resetSuccess",
  "passwordsDoNotMatch",
  "passwordTooWeak",
  "forgotPasswordSuccess",
  "genericError",
  "retry",
];

console.log(`Checking ${LOCALES.length} locales in AUTH_DICTIONARY...`);

let errors = 0;
for (const locale of LOCALES) {
  const code = locale.code;
  const dict = AUTH_DICTIONARY[code];
  if (!dict) {
    console.error(`Missing dictionary entry for locale: ${code}`);
    errors++;
    continue;
  }

  for (const key of requiredKeys) {
    const val = dict[key];
    if (typeof val !== "string" || val.trim().length === 0) {
      console.error(`Locale ${code} missing key: ${key}`);
      errors++;
    }
  }
}

// Check French values for all specific required user strings
const fr = getAuthStrings("fr");
const expectedFrSubstrings = [
  { key: "email", expected: "Email professionnel" },
  { key: "password", expected: "Mot de passe" },
  { key: "loginSubmit", expected: "Se connecter" },
  { key: "forgotPasswordLink", expected: "Mot de passe oublié ?" },
  { key: "forgotPasswordTitle", expected: "Réinitialiser le mot de passe" },
  { key: "emailAddress", expected: "Adresse email" },
  { key: "sendResetLink", expected: "Envoyer le lien" },
  { key: "backToLogin", expected: "Retour à la connexion" },
  { key: "newPassword", expected: "Nouveau mot de passe" },
  { key: "confirmPassword", expected: "Confirmer le mot de passe" },
  { key: "resetSubmit", expected: "Modifier le mot de passe" },
  { key: "linkExpired", expected: "Lien expiré" },
  { key: "linkInvalid", expected: "Lien invalide" },
  { key: "resetSuccess", expected: "Mot de passe modifié avec succès" },
  { key: "passwordsDoNotMatch", expected: "Les mots de passe ne correspondent pas" },
  { key: "passwordTooWeak", expected: "Mot de passe trop faible" },
  { key: "forgotPasswordSuccess", expected: "Si un compte existe avec cette adresse" },
  { key: "genericError", expected: "Une erreur est survenue" },
  { key: "retry", expected: "Réessayer" },
  { key: "backToHome", expected: "Retour à l’accueil" },
  { key: "createOrgLink", expected: "Créer une organisation" },
  { key: "badgeLogin", expected: "Espace sécurisé" },
  { key: "subheadingLogin", expected: "Accédez à votre espace Avenqo" },
];

for (const exp of expectedFrSubstrings) {
  const actual = fr[exp.key as keyof AuthStrings];
  if (!actual.includes(exp.expected)) {
    console.error(`FR key ${exp.key} expected to contain "${exp.expected}", got "${actual}"`);
    errors++;
  }
}

if (errors > 0) {
  console.error(`FAILED: ${errors} errors found in i18n validation.`);
  process.exit(1);
} else {
  console.log(`SUCCESS: All ${LOCALES.length} locales verified with all 54 required auth keys!`);
}
