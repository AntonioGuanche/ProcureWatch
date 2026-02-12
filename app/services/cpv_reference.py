"""
CPV (Common Procurement Vocabulary) reference data.
Used for the landing page CPV dropdown and search filters.
"""

# Most commonly used CPV codes in Belgian/EU procurement
# Format: (code, label_fr)
CPV_REFERENCE: list[tuple[str, str]] = [
    # ── Construction (45) ──
    ("45000000", "Travaux de construction"),
    ("45100000", "Préparation de chantier"),
    ("45110000", "Démolition et terrassement"),
    ("45111000", "Travaux de démolition"),
    ("45112000", "Travaux d'excavation et terrassement"),
    ("45200000", "Travaux de construction complète ou partielle"),
    ("45210000", "Construction de bâtiments"),
    ("45213000", "Construction de bâtiments commerciaux et industriels"),
    ("45214000", "Construction d'établissements scolaires et de recherche"),
    ("45215000", "Construction de bâtiments de santé"),
    ("45220000", "Ouvrages d'art et de génie civil"),
    ("45230000", "Travaux de pipelines, lignes de communication et d'énergie"),
    ("45231000", "Travaux de construction de pipelines"),
    ("45232000", "Travaux d'assainissement et de surface"),
    ("45233000", "Travaux de voirie et autoroutes"),
    ("45233100", "Travaux de construction de routes"),
    ("45233200", "Travaux de revêtement divers"),
    ("45233300", "Travaux de fondation de routes"),
    ("45234000", "Travaux de construction de chemins de fer"),
    ("45240000", "Construction d'ouvrages hydrauliques"),
    ("45260000", "Travaux de couverture et charpente"),
    ("45261000", "Travaux de charpente et de couverture"),
    ("45262000", "Travaux spéciaux de construction"),
    ("45300000", "Travaux d'installation"),
    ("45310000", "Travaux d'installation électrique"),
    ("45311000", "Câblage et installations électriques"),
    ("45312000", "Installation de systèmes d'alarme et d'antennes"),
    ("45314000", "Installation de matériel de télécommunications"),
    ("45315000", "Installation de chauffage électrique"),
    ("45320000", "Travaux d'isolation"),
    ("45321000", "Travaux d'isolation thermique"),
    ("45330000", "Travaux de plomberie"),
    ("45331000", "Installation de chauffage, ventilation et climatisation"),
    ("45332000", "Travaux de plomberie et de pose de conduites d'évacuation"),
    ("45333000", "Installation de gaz"),
    ("45340000", "Installation de clôtures, garde-corps et sécurité"),
    ("45343000", "Travaux d'installation de dispositifs anti-incendie"),
    ("45400000", "Travaux de parachèvement de bâtiment"),
    ("45410000", "Travaux de plâtrerie"),
    ("45420000", "Travaux de menuiserie et charpenterie"),
    ("45421000", "Travaux de menuiserie"),
    ("45430000", "Revêtement de sols et de murs"),
    ("45431000", "Travaux de carrelage"),
    ("45432000", "Pose et revêtement de sols"),
    ("45440000", "Travaux de peinture et vitrerie"),
    ("45441000", "Travaux de vitrerie"),
    ("45442000", "Travaux de peinture"),
    ("45443000", "Travaux de ravalement"),
    ("45450000", "Autres travaux de parachèvement de bâtiment"),
    ("45453000", "Travaux de remise en état et de remise à neuf"),
    ("45500000", "Location de machines de construction avec opérateur"),

    # ── Espaces verts / Agriculture (03, 77) ──
    ("03400000", "Produits de la sylviculture et de l'exploitation forestière"),
    ("03440000", "Produits de la sylviculture"),
    ("77000000", "Services agricoles, sylvicoles et horticoles"),
    ("77200000", "Services sylvicoles"),
    ("77210000", "Services de débardage"),
    ("77211000", "Services d'abattage d'arbres"),
    ("77300000", "Services horticoles"),
    ("77310000", "Réalisation et entretien d'espaces verts"),
    ("77311000", "Entretien de jardins d'agrément"),
    ("77312000", "Services de désherbage"),
    ("77313000", "Services d'entretien de parcs"),
    ("77314000", "Services d'entretien de terrains"),
    ("77315000", "Services d'ensemencement"),
    ("77340000", "Élagage des arbres et taille des haies"),
    ("77341000", "Élagage des arbres"),
    ("77342000", "Taille des haies"),

    # ── IT / Logiciel (48, 72) ──
    ("48000000", "Logiciels et systèmes informatiques"),
    ("48100000", "Logiciels spécifiques à l'industrie"),
    ("48200000", "Logiciels de réseau, internet et intranet"),
    ("48300000", "Logiciels de création de documents et de gestion"),
    ("48400000", "Logiciels de gestion de transactions et personnels"),
    ("48600000", "Logiciels de bases de données et d'exploitation"),
    ("48700000", "Logiciels utilitaires"),
    ("48800000", "Systèmes et serveurs informatiques"),
    ("48900000", "Logiciels et systèmes informatiques divers"),
    ("72000000", "Services de technologies de l'information"),
    ("72100000", "Services de conseil en matériel informatique"),
    ("72200000", "Services de programmation et de conseil en logiciels"),
    ("72210000", "Services de programmation de logiciels"),
    ("72220000", "Services de conseil en systèmes et technique"),
    ("72230000", "Services de développement de logiciels personnalisés"),
    ("72240000", "Services d'analyse et de programmation de systèmes"),
    ("72250000", "Services de maintenance de systèmes et d'assistance"),
    ("72260000", "Services liés aux logiciels"),
    ("72300000", "Services de saisie de données"),
    ("72400000", "Services internet"),
    ("72500000", "Services informatiques"),
    ("72600000", "Services d'assistance et de conseil informatiques"),
    ("72700000", "Services de réseaux informatiques"),
    ("72800000", "Services d'audit et de test informatiques"),
    ("72900000", "Services de sauvegarde et de conversion informatiques"),

    # ── Nettoyage (90) ──
    ("90000000", "Services d'évacuation des eaux usées et d'élimination des déchets"),
    ("90500000", "Services liés aux déchets et aux ordures"),
    ("90510000", "Élimination et traitement des ordures"),
    ("90511000", "Services de collecte des ordures"),
    ("90512000", "Services de transport des ordures"),
    ("90600000", "Services de nettoyage et d'hygiène urbains"),
    ("90610000", "Services de nettoyage et de balayage des rues"),
    ("90620000", "Services de déneigement"),
    ("90630000", "Services de déverglaçage"),
    ("90900000", "Services de nettoyage et d'hygiène"),
    ("90910000", "Services de nettoyage"),
    ("90911000", "Services de nettoyage de logements et de bâtiments"),
    ("90911200", "Services de nettoyage de bâtiments"),
    ("90914000", "Services de nettoyage de parkings"),
    ("90919000", "Services de nettoyage de bureaux et d'écoles"),
    ("90920000", "Services d'hygiène relatifs aux installations"),
    ("90921000", "Services de désinfection et de désinfestation"),

    # ── Sécurité (79, 35) ──
    ("35100000", "Matériel de secours et de sécurité"),
    ("79700000", "Services d'enquête et de sécurité"),
    ("79710000", "Services de sécurité"),
    ("79711000", "Services de surveillance d'installations d'alarme"),
    ("79713000", "Services de gardiennage"),
    ("79714000", "Services de surveillance"),

    # ── Transport (60, 34) ──
    ("34100000", "Véhicules à moteur"),
    ("34110000", "Voitures particulières"),
    ("34130000", "Véhicules à moteur servant au transport de marchandises"),
    ("34144000", "Véhicules à moteur à usage spécial"),
    ("60000000", "Services de transport"),
    ("60100000", "Services de transport routier"),
    ("60112000", "Services de transport routier public"),
    ("60130000", "Services spéciaux de transport routier de passagers"),
    ("60140000", "Transport non régulier de passagers"),

    # ── Architecture / Ingénierie (71) ──
    ("71000000", "Services d'architecture, de construction et d'ingénierie"),
    ("71200000", "Services d'architecture"),
    ("71210000", "Services de conseil en architecture"),
    ("71220000", "Services de création architecturale"),
    ("71240000", "Services d'architecture, d'ingénierie et de planification"),
    ("71300000", "Services d'ingénierie"),
    ("71310000", "Services de conseil en matière d'ingénierie et de construction"),
    ("71320000", "Services de conception technique"),
    ("71330000", "Services divers d'ingénierie"),
    ("71350000", "Services à caractère scientifique et technique"),
    ("71400000", "Services d'urbanisme et d'architecture paysagère"),
    ("71500000", "Services liés à la construction"),
    ("71520000", "Services de conduite de travaux"),
    ("71540000", "Services de gestion de la construction"),
    ("71600000", "Services d'essais techniques, d'analyses et de conseil"),

    # ── Mobilier / Fournitures (39, 30) ──
    ("30000000", "Machines de bureau et matériel informatique"),
    ("30200000", "Matériel et fournitures informatiques"),
    ("30210000", "Machines de traitement des données (matériel)"),
    ("30230000", "Matériel informatique"),
    ("39000000", "Meubles, aménagement, appareils électroménagers"),
    ("39100000", "Mobilier"),
    ("39110000", "Sièges, chaises et articles assimilés"),
    ("39130000", "Mobilier de bureau"),
    ("39150000", "Mobilier et équipements divers"),
    ("39200000", "Aménagements"),
    ("39300000", "Équipement divers"),

    # ── Restauration (55) ──
    ("55000000", "Services d'hôtellerie, de restauration et de commerce au détail"),
    ("55300000", "Services de restaurant et de service de repas"),
    ("55320000", "Services de repas"),
    ("55400000", "Services de débit de boissons"),
    ("55500000", "Services de cantine et de restauration collective"),
    ("55520000", "Services traiteur"),
    ("55521000", "Services traiteur pour ménages"),
    ("55523000", "Services traiteur pour autres entreprises ou institutions"),

    # ── Formation (80) ──
    ("80000000", "Services d'enseignement et de formation"),
    ("80100000", "Services d'enseignement primaire"),
    ("80200000", "Services d'enseignement secondaire"),
    ("80300000", "Services d'enseignement supérieur"),
    ("80400000", "Services d'éducation des adultes et autres"),
    ("80500000", "Services de formation"),
    ("80510000", "Services de formation spécialisée"),
    ("80530000", "Services de formation professionnelle"),

    # ── Santé / Social (85, 33) ──
    ("33000000", "Matériels médicaux, pharmaceutiques et de soins personnels"),
    ("33100000", "Équipements médicaux"),
    ("33600000", "Produits pharmaceutiques"),
    ("85000000", "Services de santé et services sociaux"),
    ("85100000", "Services de santé"),
    ("85110000", "Services hospitaliers et services connexes"),
    ("85140000", "Services de santé divers"),
    ("85300000", "Services d'action sociale et services connexes"),

    # ── Énergie (09, 65) ──
    ("09000000", "Produits pétroliers, combustibles et électricité"),
    ("09100000", "Combustibles"),
    ("09300000", "Électricité, chauffage, énergie solaire et nucléaire"),
    ("09310000", "Électricité"),
    ("65000000", "Services publics"),
    ("65100000", "Distribution d'eau et services connexes"),
    ("65300000", "Distribution d'électricité et services connexes"),
    ("65400000", "Autres sources d'approvisionnement en énergie"),

    # ── Communication / Marketing (79) ──
    ("79000000", "Services aux entreprises"),
    ("79100000", "Services juridiques"),
    ("79110000", "Services de conseil et de représentation juridiques"),
    ("79200000", "Services de comptabilité, d'audit et fiscaux"),
    ("79210000", "Services de comptabilité et d'audit"),
    ("79300000", "Études de marché et recherche économique"),
    ("79340000", "Services de publicité et de marketing"),
    ("79341000", "Services de publicité"),
    ("79400000", "Conseil en affaires et en gestion"),
    ("79500000", "Services de secrétariat et de soutien"),
    ("79530000", "Services de traduction"),
    ("79600000", "Services de recrutement"),
    ("79800000", "Services d'impression et services connexes"),
    ("79810000", "Services d'impression"),
    ("79820000", "Services relatifs à l'impression"),
    ("79900000", "Services divers aux entreprises"),

    # ── Assurance / Finance (66) ──
    ("66000000", "Services financiers et d'assurance"),
    ("66100000", "Services bancaires et d'investissement"),
    ("66500000", "Services d'assurance et de retraite"),
    ("66510000", "Services d'assurance"),

    # ── Textile / Vêtements (18) ──
    ("18000000", "Vêtements, articles chaussants et bagages"),
    ("18100000", "Vêtements professionnels et spéciaux"),
    ("18110000", "Vêtements professionnels"),
    ("18130000", "Vêtements de travail spéciaux"),
    ("18200000", "Vêtements de dessus"),
    ("18300000", "Articles d'habillement"),
    ("18400000", "Vêtements spéciaux et accessoires"),
    ("18800000", "Articles chaussants"),

    # ── Alimentation (15) ──
    ("15000000", "Produits alimentaires, boissons, tabac"),
    ("15100000", "Produits de l'élevage, viandes et produits à base de viande"),
    ("15200000", "Poisson préparé et en conserve"),
    ("15300000", "Fruits, légumes et produits connexes"),
    ("15400000", "Huiles et graisses animales ou végétales"),
    ("15500000", "Produits laitiers"),
    ("15600000", "Produits de minoterie, amidon et féculents"),
    ("15800000", "Produits alimentaires divers"),
    ("15900000", "Boissons, tabac et produits connexes"),

    # ── Réparation / Maintenance (50) ──
    ("50000000", "Services de réparation et d'entretien"),
    ("50100000", "Services de réparation et d'entretien de véhicules"),
    ("50200000", "Services de réparation et d'entretien d'aéronefs"),
    ("50300000", "Services de réparation et d'entretien de matériel informatique"),
    ("50400000", "Services de réparation et d'entretien de matériel médical"),
    ("50500000", "Services de réparation et d'entretien de pompes"),
    ("50700000", "Services de réparation et d'entretien d'installations de bâtiments"),
    ("50710000", "Services de réparation et d'entretien d'équipements électriques et mécaniques"),
    ("50720000", "Services de réparation et d'entretien de chauffage central"),
    ("50730000", "Services de réparation et d'entretien de groupes réfrigérants"),
    ("50800000", "Services divers d'entretien et de réparation"),
    ("50850000", "Services de réparation et d'entretien de mobilier"),

    # ── Télécom (64, 32) ──
    ("32000000", "Équipements et appareils de radio, TV et communication"),
    ("32400000", "Réseaux"),
    ("32500000", "Matériel de télécommunications"),
    ("64000000", "Services des postes et télécommunications"),
    ("64200000", "Services de télécommunications"),
    ("64210000", "Services de téléphone et de transmission de données"),
    ("64220000", "Services de télécommunications sauf téléphone"),

    # ── Loisirs / Culture (92) ──
    ("92000000", "Services récréatifs, culturels et sportifs"),
    ("92300000", "Services de divertissement"),
    ("92500000", "Services de bibliothèques, d'archives, de musées"),
    ("92600000", "Services sportifs"),

    # ── Immobilier (70) ──
    ("70000000", "Services immobiliers"),
    ("70100000", "Services immobiliers relatifs aux biens propres"),
    ("70200000", "Services de location ou de crédit-bail"),
    ("70300000", "Services d'agents immobiliers"),

    # ── R&D (73) ──
    ("73000000", "Services de recherche et développement"),
    ("73100000", "Services de recherche et de développement expérimental"),
    ("73300000", "Conception et exécution de R&D"),
]


def search_cpv(query: str, limit: int = 20) -> list[dict[str, str]]:
    """Search CPV codes by code prefix or label keyword."""
    q = query.lower().strip()
    if not q:
        return [{"code": code, "label": label} for code, label in CPV_REFERENCE[:limit]]

    results = []
    for code, label in CPV_REFERENCE:
        if q in code or q in label.lower():
            results.append({"code": code, "label": label})
            if len(results) >= limit:
                break
    return results
