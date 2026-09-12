"use client";

import React, { useState } from "react";
import {
  H1,
  H2,
  H3,
  Text,
  TextMuted,
  Badge,
  Button,
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  StatCard,
  Input,
  Select,
  Textarea,
  FormField,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TrendSparkline,
  MiniBarChart,
  ComparisonProgress,
  Skeleton,
  CardSkeleton,
  TableRowSkeleton,
  EmptyState,
  SuccessState,
  ErrorState,
  AIState,
  Modal,
  Drawer,
} from "@/components/ui";
import { ThemeToggle } from "@/components/theme-toggle";
import {
  Sparkles,
  TrendingUp,
  DollarSign,
  Users,
  ShieldCheck,
  Search,
  SlidersHorizontal,
  Mail,
  ArrowRight,
  RefreshCw,
} from "lucide-react";

export default function DesignSystemShowcasePage() {
  const [modalOpen, setModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [btnLoading, setBtnLoading] = useState(false);

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-950 text-neutral-900 dark:text-neutral-100 transition-colors duration-200">
      {/* Top sticky bar */}
      <header className="sticky top-0 z-40 border-b border-neutral-200/80 dark:border-neutral-800 bg-white/80 dark:bg-neutral-900/80 backdrop-blur-md px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-neutral-900 text-white dark:bg-white dark:text-neutral-900 font-bold text-base shadow-xs">
            A
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold tracking-tight text-neutral-900 dark:text-neutral-100 text-sm">
                AVENQO
              </span>
              <Badge variant="ai">Design System v2.0</Badge>
              <Badge variant="success">Phase 16 Validée</Badge>
            </div>
            <p className="text-xs text-neutral-500 dark:text-neutral-400">
              International Enterprise Multi-Tenant Visual Standard
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <ThemeToggle />
          <Button
            variant="ai"
            size="sm"
            leftIcon={<Sparkles className="w-3.5 h-3.5" />}
            onClick={() => {
              setBtnLoading(true);
              setTimeout(() => setBtnLoading(false), 1200);
            }}
            isLoading={btnLoading}
          >
            Interroger AI Central
          </Button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-10 space-y-16">
        {/* Section: Overview & Philosophy */}
        <div className="space-y-3">
          <H1>Design System Ultra Premium</H1>
          <TextMuted className="max-w-3xl text-base">
            Architecture visuelle unifiée pour la plateforme AVENQO. Conforme aux standards SaaS
            B2B internationaux : typographie structurée, contrastes calibrés en mode sombre/clair,
            grounding réel IA distingué des projections financières, et composants réactifs
            mobiles/desktop.
          </TextMuted>
        </div>

        {/* Section 1: AI States & Grounding Banners */}
        <section className="space-y-4">
          <H2>1. AI Grounding & Signature States</H2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <AIState
              status="grounded"
              modelBadge="Claude 3.5 Sonnet / Multi-Agents"
              confidence={0.98}
              message="Synthèse cross-agent validée sur PostgreSQL Railway : 1 245 transactions et 682 clients certifiés."
            />
            <AIState
              status="predicted"
              modelBadge="Accounting AI Engine"
              confidence={0.84}
              message="Projection de trésorerie à J+30 basée sur le comportement d'encaissement historique (non audité)."
            />
          </div>
        </section>

        {/* Section 2: Typography & Badges */}
        <section className="space-y-4">
          <H2>2. Typographie & Badges Sémantiques</H2>
          <Card>
            <CardContent className="space-y-6 pt-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-baseline">
                <div className="space-y-2">
                  <H1>H1 Titre Principal (30px/Bold)</H1>
                  <H2>H2 Section Métier (24px/Semibold)</H2>
                  <H3>H3 Sous-Section & Module (20px/Semibold)</H3>
                  <Text>Corps de texte principal standard avec contraste élevé et lisibilité optimale.</Text>
                  <TextMuted>Texte secondaire ou métadonnées avec nuance atténuée neutre.</TextMuted>
                </div>

                <div className="space-y-4">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
                    Badges Sémantiques Métier
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="default">Standard</Badge>
                    <Badge variant="outline">Neutre Outline</Badge>
                    <Badge variant="success">Confirmé / Réconcilié</Badge>
                    <Badge variant="warning">En attente / Risque moyen</Badge>
                    <Badge variant="error">Alerte critique / Impayé</Badge>
                    <Badge variant="ai">Agent Autonome IA</Badge>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </section>

        {/* Section 3: Stat Cards & Visualizations */}
        <section className="space-y-4">
          <H2>3. Métriques & Data Visualisation Pure SVG</H2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              title="Chiffre d'Affaires Mensuel"
              value="128 450 €"
              change="+14.2%"
              changeType="positive"
              subtitle="vs mois précédent"
              icon={<DollarSign className="w-5 h-5" />}
            />
            <StatCard
              title="Clients Actifs (CRM)"
              value="1 420"
              change="+8.7%"
              changeType="positive"
              subtitle="nouveaux leads qualifiés"
              icon={<Users className="w-5 h-5" />}
            />
            <StatCard
              title="Taux de Recouvrement"
              value="96.4%"
              change="+2.1%"
              changeType="positive"
              subtitle="délai moyen 18 jours"
              icon={<TrendingUp className="w-5 h-5" />}
            />
            <StatCard
              title="Indice de Conformité"
              value="99.8%"
              subtitle="Certifié Multi-Tenant"
              icon={<ShieldCheck className="w-5 h-5" />}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4">
            <Card>
              <CardHeader>
                <CardTitle>Tendance d'Encaissements (Sparklines)</CardTitle>
                <CardDescription>Flux net réel sur les 12 dernières semaines</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between p-3 rounded-lg bg-neutral-50 dark:bg-neutral-800/40">
                  <div>
                    <p className="text-xs font-semibold text-neutral-900 dark:text-neutral-100">
                      Entrées de Trésorerie
                    </p>
                    <p className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">+18.4%</p>
                  </div>
                  <TrendSparkline
                    data={[45, 52, 49, 62, 58, 71, 68, 79, 82, 94]}
                    color="emerald"
                    width={180}
                    height={40}
                  />
                </div>

                <div className="flex items-center justify-between p-3 rounded-lg bg-neutral-50 dark:bg-neutral-800/40">
                  <div>
                    <p className="text-xs font-semibold text-neutral-900 dark:text-neutral-100">
                      Coûts d'Acquisition (CAC)
                    </p>
                    <p className="text-xs text-blue-600 dark:text-blue-400 font-medium">-12.1% optimisé</p>
                  </div>
                  <TrendSparkline
                    data={[85, 78, 82, 70, 68, 62, 55, 50, 48, 42]}
                    color="blue"
                    width={180}
                    height={40}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Activité Hebdomadaire & Objectifs</CardTitle>
                <CardDescription>Volume de transactions traitées par les agents</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <MiniBarChart
                  data={[
                    { label: "Lun", value: 340 },
                    { label: "Mar", value: 420 },
                    { label: "Mer", value: 510 },
                    { label: "Jeu", value: 480 },
                    { label: "Ven", value: 620 },
                    { label: "Sam", value: 290 },
                    { label: "Dim", value: 180 },
                  ]}
                  height={90}
                  color="blue"
                />
                <ComparisonProgress
                  label="Objectif d'automatisation IA mensuel"
                  value={8420}
                  target={10000}
                  unit="requêtes"
                />
              </CardContent>
            </Card>
          </div>
        </section>

        {/* Section 4: Enterprise Data Table */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <H2>4. Enterprise Data Table</H2>
              <TextMuted>Formatage structuré, badges sémantiques et actions contextuelles</TextMuted>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                leftIcon={<SlidersHorizontal className="w-3.5 h-3.5" />}
                onClick={() => setDrawerOpen(true)}
              >
                Filtres Avancés
              </Button>
              <Button
                variant="primary"
                size="sm"
                leftIcon={<ArrowRight className="w-3.5 h-3.5" />}
                onClick={() => setModalOpen(true)}
              >
                Ouvrir Modal
              </Button>
            </div>
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Référence Facture</TableHead>
                <TableHead>Client / Tenant</TableHead>
                <TableHead>Montant HT</TableHead>
                <TableHead>Statut Rapprochement</TableHead>
                <TableHead>Grounding Agent</TableHead>
                <TableHead align="right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell className="font-semibold text-neutral-900 dark:text-neutral-100">
                  FAC-2026-0042
                </TableCell>
                <TableCell>Société Générale des Eaux</TableCell>
                <TableCell className="font-mono font-medium">14 250,00 €</TableCell>
                <TableCell>
                  <Badge variant="success">Rapproché à 100%</Badge>
                </TableCell>
                <TableCell>
                  <Badge variant="ai">Accounting AI</Badge>
                </TableCell>
                <TableCell align="right">
                  <Button variant="ghost" size="sm" onClick={() => setDrawerOpen(true)}>
                    Inspecter
                  </Button>
                </TableCell>
              </TableRow>

              <TableRow>
                <TableCell className="font-semibold text-neutral-900 dark:text-neutral-100">
                  FAC-2026-0043
                </TableCell>
                <TableCell>Alliance Logistique Nord</TableCell>
                <TableCell className="font-mono font-medium">8 910,00 €</TableCell>
                <TableCell>
                  <Badge variant="warning">Échéance J-3</Badge>
                </TableCell>
                <TableCell>
                  <Badge variant="ai">CRM + Finance</Badge>
                </TableCell>
                <TableCell align="right">
                  <Button variant="ghost" size="sm" onClick={() => setDrawerOpen(true)}>
                    Inspecter
                  </Button>
                </TableCell>
              </TableRow>

              <TableRow>
                <TableCell className="font-semibold text-neutral-900 dark:text-neutral-100">
                  FAC-2026-0044
                </TableCell>
                <TableCell>Horizon Retail Group</TableCell>
                <TableCell className="font-mono font-medium">23 400,00 €</TableCell>
                <TableCell>
                  <Badge variant="error">Litige Encaissement</Badge>
                </TableCell>
                <TableCell>
                  <Badge variant="ai">Cross-Agent Hub</Badge>
                </TableCell>
                <TableCell align="right">
                  <Button variant="ghost" size="sm" onClick={() => setDrawerOpen(true)}>
                    Inspecter
                  </Button>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </section>

        {/* Section 5: Buttons & Form Controls */}
        <section className="space-y-4">
          <H2>5. Boutons, Formulaires & États d'Interaction</H2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Palette de Boutons</CardTitle>
                <CardDescription>États standard, hover, active, loading et disabled</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap gap-2.5">
                  <Button variant="primary">Principal</Button>
                  <Button variant="secondary">Secondaire</Button>
                  <Button variant="outline">Contour</Button>
                  <Button variant="ghost">Fantôme</Button>
                  <Button variant="ai" leftIcon={<Sparkles className="w-4 h-4" />}>
                    Bouton IA
                  </Button>
                  <Button variant="danger">Supprimer</Button>
                </div>
                <div className="flex flex-wrap gap-2.5 pt-2">
                  <Button size="sm">Petit</Button>
                  <Button size="md">Moyen</Button>
                  <Button size="lg">Grand</Button>
                  <Button isLoading size="md">
                    Chargement
                  </Button>
                  <Button disabled size="md">
                    Désactivé
                  </Button>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Champs de Saisie & Contrôles</CardTitle>
                <CardDescription>Icônes contextuelles, validation d'erreurs et hints</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField label="Recherche Plein Texte" hint="Filtrage instantané">
                  <Input
                    placeholder="Filtrer transactions, clients, SKU..."
                    leftIcon={<Search className="w-4 h-4" />}
                  />
                </FormField>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <FormField label="Sélection de Domaine">
                    <Select
                      options={[
                        { label: "Cross-Agent Synergy", value: "cross_agent" },
                        { label: "Retail Intelligence", value: "retail" },
                        { label: "CRM AI", value: "crm" },
                        { label: "Accounting AI", value: "accounting" },
                      ]}
                    />
                  </FormField>
                  <FormField label="Email de Notification" required>
                    <Input
                      type="email"
                      placeholder="tenant@enterprise.com"
                      leftIcon={<Mail className="w-4 h-4" />}
                    />
                  </FormField>
                </div>
              </CardContent>
            </Card>
          </div>
        </section>

        {/* Section 6: Skeletons & Fallback States */}
        <section className="space-y-4">
          <H2>6. Skeletons & États Feedback</H2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <CardSkeleton />
            <EmptyState
              title="Aucun litige en cours"
              description="Toutes les factures du trimestre courant sont parfaitement rapprochées."
              actionLabel="Consulter l'historique"
              onAction={() => {}}
            />
            <SuccessState
              title="Synchronisation Réussie"
              description="1 245 écritures importées depuis le grand livre PostgreSQL."
              actionLabel="Télécharger le rapport"
              onAction={() => {}}
            />
          </div>
        </section>
      </main>

      {/* Interactive Modal */}
      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Détail de Synthèse Cross-Agent"
        description="Grounding vérifié sur PostgreSQL Railway (altaria.proxy.rlwy.net:17860)"
      >
        <div className="space-y-4 text-sm">
          <AIState
            status="grounded"
            confidence={0.97}
            message="Données réelles agrégées à travers Retail, CRM et Accounting."
          />
          <div className="p-3 rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-800/50 space-y-2">
            <div className="flex justify-between">
              <span className="text-neutral-500">Tenant ID</span>
              <span className="font-mono text-xs font-semibold">9c97cb94-e9f9-46fb-afd4-8a1d21019cff</span>
            </div>
            <div className="flex justify-between">
              <span className="text-neutral-500">Cross-Agent Health Score</span>
              <span className="font-semibold text-emerald-600">88.5 / 100</span>
            </div>
            <div className="flex justify-between">
              <span className="text-neutral-500">Statut Réconciliation</span>
              <span className="font-semibold text-blue-600">Zero Écart Comptable</span>
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={() => setModalOpen(false)}>
              Fermer
            </Button>
            <Button variant="primary" size="sm" onClick={() => setModalOpen(false)}>
              Confirmer l'Audit
            </Button>
          </div>
        </div>
      </Modal>

      {/* Interactive Drawer */}
      <Drawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="Inspection Métier Approfondie"
        description="Paramètres et télémétrie de l'agent"
        size="md"
      >
        <div className="space-y-6 text-sm">
          <FormField label="Statut de l'Agent Autonome">
            <Select
              options={[
                { label: "Surveillance Continue (Actif)", value: "active" },
                { label: "Mode Lecture Seule (Auditeur)", value: "readonly" },
                { label: "Mode Pause Manuelle", value: "paused" },
              ]}
            />
          </FormField>

          <FormField label="Instruction Contextuelle">
            <Textarea
              rows={4}
              defaultValue="Surveiller les comptes clients dont le délai de paiement dépasse 30 jours et déclencher une alerte combinée CRM + Comptabilité."
            />
          </FormField>

          <div className="p-4 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-800/40 space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-600 dark:text-neutral-400">
              Audit Logs Récents
            </h4>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between text-neutral-500">
                <span>Rapprochement automatique</span>
                <span>Il y a 4 min</span>
              </div>
              <div className="flex justify-between text-neutral-500">
                <span>Synchronisation CRM Leads</span>
                <span>Il y a 12 min</span>
              </div>
              <div className="flex justify-between text-neutral-500">
                <span>Vérification d'intégrité tenant</span>
                <span>Il y a 28 min</span>
              </div>
            </div>
          </div>

          <div className="pt-4 flex gap-2">
            <Button variant="primary" className="flex-1" onClick={() => setDrawerOpen(false)}>
              Enregistrer
            </Button>
            <Button variant="outline" onClick={() => setDrawerOpen(false)}>
              Annuler
            </Button>
          </div>
        </div>
      </Drawer>
    </div>
  );
}
