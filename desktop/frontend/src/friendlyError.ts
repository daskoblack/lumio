/**
 * Traduit les messages d'erreur techniques en explications utilisables.
 *
 * Lumio s'adresse à des enseignants, pas à des développeurs : un message
 * comme « L'OCR n'est pas géré dans ce MVP » ou « Commande échouée (ffmpeg) »
 * ne dit ni ce qui s'est passé, ni quoi faire. Chaque règle ci-dessous
 * explique la cause ET propose une action concrète.
 *
 * L'ordre compte : les règles les plus spécifiques d'abord. Un message non
 * reconnu est affiché tel quel — mieux vaut un texte technique qu'un « une
 * erreur est survenue » qui ne laisse aucune piste.
 */

type Rule = { match: (m: string) => boolean; message: string };

const has = (...fragments: string[]) => (m: string) =>
  fragments.some((f) => m.toLowerCase().includes(f.toLowerCase()));

const RULES: Rule[] = [
  // --- Configuration de l'IA ---------------------------------------------
  {
    match: has('Aucun fournisseur', '_API_KEY', 'Clé API'),
    message:
      "Aucune intelligence artificielle n'est configurée. Va dans Réglages "
      + 'pour coller un code — ils sont gratuits, et un seul suffit pour commencer.',
  },
  {
    match: has('Tous les fournisseurs'),
    message:
      "Tes intelligences artificielles ont épuisé leur réserve du jour. "
      + 'Ajoute un autre code dans Réglages pour agrandir ta réserve, ou reprends '
      + 'demain — elle repart à zéro chaque jour.',
  },
  {
    match: has('does not exist', 'model_not_found', 'Fournisseur LLM inconnu'),
    message:
      "L'intelligence artificielle utilisée par Lumio n'est plus disponible. "
      + "Installe la dernière version de Lumio depuis le site : elle corrige ce genre "
      + 'de changement côté fournisseur.',
  },

  // --- Le document fourni -------------------------------------------------
  {
    match: has("pas assez de texte exploitable", 'OCR'),
    message:
      "Ce PDF ne contient pas de texte sélectionnable : c'est probablement un "
      + 'document scanné, ou une suite d\'images. Lumio a besoin d\'un PDF dont le '
      + 'texte peut être copié — réexporte ton cours depuis Word, PowerPoint ou '
      + 'Google Docs plutôt que depuis un scan.',
  },
  {
    match: has('Fichier introuvable'),
    message:
      "Ce fichier est introuvable. Il a peut-être été déplacé, renommé ou "
      + 'supprimé depuis que tu l\'as choisi. Sélectionne-le à nouveau.',
  },
  {
    match: has('PDF illisible'),
    message:
      "Ce PDF n'a pas pu être ouvert : il est peut-être abîmé ou protégé par "
      + 'un mot de passe. Essaie de l\'ouvrir puis de le réenregistrer, ou choisis '
      + 'un autre fichier.',
  },

  // --- Voix et son --------------------------------------------------------
  {
    match: has("n'a produit aucun son", 'No audio'),
    message:
      "La voix n'a produit aucun son. Vérifie ta connexion internet — elle est "
      + 'nécessaire pour enregistrer la narration — puis réessaie.',
  },
  {
    // Volontairement ancré sur la phrase complète : chercher le seul mot
    // « voix » attraperait toute erreur de synthèse, y compris une coupure
    // réseau, et donnerait un conseil trompeur.
    match: has("n'existe plus dans le catalogue"),
    message:
      "La voix choisie n'est plus disponible. Va dans Réglages pour en "
      + 'sélectionner une autre, puis réessaie.',
  },
  {
    match: has('Rien à prononcer'),
    message:
      "Cette page ne contient rien qui puisse être lu à voix haute (elle est "
      + "peut-être vide, ou uniquement composée d'images). Retire-la du PDF, ou "
      + 'ajoutes-y un peu de texte.',
  },

  // --- Réseau -------------------------------------------------------------
  {
    match: has('Timeout', 'timed out', 'Connection', 'connexion', 'Network', 'getaddrinfo'),
    message:
      'La connexion internet semble interrompue. Lumio en a besoin pour écrire '
      + 'le texte et enregistrer la voix. Vérifie ta connexion, puis réessaie.',
  },

  // --- Montage vidéo ------------------------------------------------------
  {
    match: has('Commande échouée', 'ffmpeg', 'ffprobe'),
    message:
      "Le montage de la vidéo a échoué. Vérifie qu'il reste de l'espace libre "
      + 'sur ton disque, puis relance la génération depuis la liste des vidéos.',
  },

  // --- Réponse de l'IA inexploitable --------------------------------------
  {
    match: has('JSON', 'Réponse vide', 'Réponse Gemini inattendue'),
    message:
      "L'intelligence artificielle a renvoyé une réponse inutilisable. C'est "
      + 'généralement passager : relance la génération.',
  },

  // --- État du cours ------------------------------------------------------
  {
    match: has('impossible depuis l', 'Job introuvable'),
    message:
      "Cette action n'est pas possible à cette étape du cours. Retourne à la "
      + 'liste des vidéos et reprends le cours depuis là.',
  },
];

export function friendlyError(message: string): string {
  for (const rule of RULES) {
    if (rule.match(message)) return rule.message;
  }
  // Non reconnu : on montre le message d'origine plutôt qu'un texte creux,
  // pour que l'utilisateur ait au moins quelque chose à transmettre.
  return `Un problème est survenu : ${message}`;
}
