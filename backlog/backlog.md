# Backlog do Projeto Web

> [!TIP]
> Este documento usa apenas Markdown "puro" (checkboxes, negrito, blockquotes de alerta). Isso garante boa renderização tanto no **Obsidian** quanto no **GitHub**, sem depender de HTML/CSS inline que o GitHub ignora.

## Definição do projeto

- [x] Definir nome do projeto

- Auto
- Fácil
- Rápido
- Prático
- Móvel
- Manutenção
- Exposição

**S A M**

**Simple Auto Maintenance**

- [x] Definir objetivo geral

Facilitar a busca e a escolha de oficinas para a manutenção e reparação de veículos, permitindo que os usuários encontrem estabelecimentos de acordo com os serviços oferecidos. A plataforma deverá apresentar informações detalhadas sobre a área de atuação de cada oficina, indicando se trabalha com manutenção geral ou se é especializada em determinados tipos de veículos, sistemas ou serviços.

Também deverão ser especificados os principais serviços disponíveis, como reparos mecânicos, manutenção elétrica, troca e reparo de pneus, alinhamento e balanceamento, serviços de funilaria e pintura, instalação de acessórios, modificações e personalizações de veículos, entre outros. Dessa forma, o usuário poderá identificar com maior facilidade quais oficinas possuem os serviços e especialistas necessários para atender às suas necessidades.

- [x] Definir objetivos específicos

Além de facilitar a busca por oficinas e serviços de manutenção e reparação de veículos, a plataforma deverá oferecer funcionalidades de comunicação, divulgação e gerenciamento, atendendo tanto aos clientes quanto aos prestadores de serviços cadastrados.

**Funcionalidades para clientes**

- **Oferecer um sistema de comunicação por chat**, permitindo que clientes entrem em contato diretamente com as oficinas para tirar dúvidas, solicitar informações, discutir serviços e negociar atendimentos.
- **Permitir a visualização de promoções e ofertas**, possibilitando que as oficinas divulguem descontos, serviços promocionais e outras condições especiais na tela inicial da plataforma.
- **Disponibilizar catálogos de produtos e itens**, permitindo que as oficinas apresentem peças, acessórios e outros produtos disponíveis para venda em seu estabelecimento.
- **Informar a disponibilidade local dos produtos**, deixando claro que o catálogo representa os itens disponíveis na própria oficina, não constituindo um sistema de comércio eletrônico.
- **Não realizar vendas diretamente pela plataforma**, mantendo a negociação, pagamento, retirada ou entrega sob responsabilidade da oficina. A negociação poderá ser realizada por meio do chat ou pelos canais de contato disponibilizados pelo estabelecimento.

**Funcionalidades exclusivas para prestadores de serviços**

Os prestadores de serviços, como oficinas e mecânicos cadastrados como empresas, deverão possuir uma área administrativa própria para o gerenciamento de seus clientes, veículos, serviços e atividades realizadas.

Entre essas funcionalidades estão:

- **Cadastro completo dos veículos dos clientes**, contendo informações como marca, modelo, ano, versão, placa, quilometragem e demais dados relevantes para a manutenção.
- **Cadastro e acompanhamento dos serviços de manutenção**, permitindo registrar quais componentes ou sistemas do veículo precisam de manutenção ou reparo.
- **Registro de peças e componentes**, possibilitando identificar quais peças foram substituídas, quais precisam ser substituídas e quais serviços estão relacionados a cada peça.
- **Elaboração de orçamentos**, permitindo que o prestador registre peças, mão de obra, serviços adicionais, valores e o custo total estimado do atendimento.
- **Acompanhamento do status do serviço**, permitindo registrar etapas como orçamento, aguardando aprovação, em manutenção, aguardando peça, serviço concluído e veículo entregue.
- **Histórico de manutenção dos veículos**, mantendo um registro dos serviços, reparos, peças substituídas e demais procedimentos realizados anteriormente.
- **Registro de observações técnicas**, permitindo ao profissional adicionar informações relevantes encontradas durante a inspeção ou manutenção do veículo.
- **Gerenciamento dos produtos e peças disponíveis na oficina**, possibilitando manter o catálogo de itens oferecidos pelo estabelecimento.
- **Gerenciamento de promoções e ofertas**, permitindo que a própria oficina cadastre, edite e remova suas promoções.
- **Gerenciamento dos atendimentos e clientes**, permitindo organizar os serviços solicitados e acompanhar os veículos que estão atualmente em manutenção.
- **Comunicação com o cliente por meio do chat**, possibilitando discutir o orçamento, esclarecer dúvidas, solicitar informações e negociar serviços ou produtos.

---

- [x] Definir público-alvo / beneficiários

A plataforma será destinada principalmente a dois grupos de usuários: **pessoas que procuram serviços relacionados à manutenção de seus veículos** e **mecânicos ou oficinas que desejam divulgar e administrar seus serviços**.

**Clientes e proprietários de veículos**

O sistema será destinado a pessoas que estejam procurando uma oficina ou um estabelecimento capaz de solucionar um problema específico em seu veículo. A busca poderá abranger desde oficinas de mecânica geral até estabelecimentos especializados em determinados serviços.

Além das oficinas, o mapa poderá apresentar outros pontos de interesse relacionados aos veículos, como **borracharias, postos de combustível com calibragem de pneus e outros estabelecimentos que ofereçam serviços automotivos específicos**. Esses estabelecimentos poderão aparecer como pontos no mapa para facilitar sua localização, mas não serão necessariamente cadastrados como oficinas dentro da plataforma.

Dessa forma, o usuário poderá utilizar o sistema não apenas para encontrar uma oficina para realizar uma manutenção completa, mas também para localizar rapidamente um estabelecimento que ofereça um serviço específico ou uma necessidade pontual.

**Mecânicos e oficinas**

A plataforma também será destinada a **mecânicos, oficinas e outros prestadores de serviços automotivos** que desejam divulgar seu trabalho, conquistar novos clientes e facilitar a comunicação com o público.

O sistema permitirá que esses profissionais mantenham um perfil próprio com informações sobre seus serviços, especialidades, localização, produtos disponíveis, promoções e formas de contato, sem a necessidade de desenvolver e manter um site próprio exclusivamente para essa finalidade.

Os prestadores também poderão utilizar as funcionalidades internas da plataforma para gerenciar clientes, veículos, serviços, peças, orçamentos e históricos de manutenção.

Além disso, os clientes poderão realizar **avaliações dos serviços e atendimentos**, permitindo que os prestadores construam sua reputação dentro da plataforma por meio da experiência dos usuários.

> [!WARNING] Localização de estabelecimentos
> O mapa será um dos principais recursos da plataforma. Ele poderá apresentar diferentes tipos de estabelecimentos relacionados ao setor automotivo, permitindo ao usuário identificar rapidamente o que existe nas proximidades.
>
> Entretanto, deverá existir uma distinção entre **pontos de interesse exibidos no mapa** e **oficinas cadastradas oficialmente na plataforma**. Borracharias, postos de combustível e outros estabelecimentos poderão ser exibidos no mapa sem necessariamente possuírem um perfil completo no sistema.
>
> Já as oficinas e prestadores que desejarem utilizar as funcionalidades completas da plataforma deverão realizar um **cadastro oficial**, permitindo que o proprietário ou responsável confirme as informações do estabelecimento, gerencie seus serviços e tenha acesso às ferramentas administrativas disponíveis para os prestadores.

- [x] Definir o problema que o projeto pretende resolver

O projeto busca solucionar dificuldades relacionadas à **localização, escolha, comunicação e gerenciamento de serviços automotivos**, tanto para proprietários de veículos quanto para mecânicos e oficinas.

**1. Dificuldade para encontrar uma oficina adequada**

Proprietários de veículos podem ter dificuldade para encontrar rapidamente uma oficina que realize o serviço necessário para um problema específico. Nem todas as oficinas oferecem os mesmos serviços, possuem os mesmos especialistas ou trabalham com os mesmos tipos de veículos.

A plataforma pretende centralizar essas informações, permitindo que o usuário pesquise oficinas de acordo com suas necessidades, serviços oferecidos, especialidades e localização.

**2. Falta de informações sobre os serviços oferecidos**

Muitas vezes, o cliente precisa entrar em contato com diferentes oficinas para descobrir se determinado serviço é realizado, se existe um profissional especializado ou se uma determinada peça ou produto está disponível.

O projeto pretende reduzir essa dificuldade permitindo que as oficinas apresentem previamente seus serviços, especialidades, produtos, peças, promoções e outras informações relevantes.

**3. Dificuldade para localizar serviços automotivos específicos**

Nem toda necessidade relacionada a um veículo exige uma oficina completa. O usuário pode precisar apenas calibrar um pneu, realizar um reparo em uma borracharia ou encontrar outro serviço específico.

O mapa pretende facilitar a localização desses estabelecimentos e pontos de interesse relacionados ao setor automotivo, permitindo que o usuário encontre alternativas próximas de acordo com sua necessidade.

**4. Dificuldade de comunicação entre clientes e oficinas**

O contato entre cliente e prestador pode ser fragmentado entre diferentes canais, dificultando a solicitação de informações, esclarecimento de dúvidas e negociação de serviços.

A plataforma pretende centralizar essa comunicação por meio de um sistema de chat, permitindo que o cliente converse diretamente com a oficina ou mecânico.

**5. Dificuldade para obter e comparar informações antes de solicitar um serviço**

O cliente pode não possuir informações suficientes para decidir qual estabelecimento procurar, especialmente quando não conhece previamente uma oficina ou mecânico.

Ao disponibilizar informações sobre serviços, especialidades, avaliações, localização, promoções e produtos, o sistema pretende oferecer ao usuário mais informações para avaliar as opções disponíveis.

**6. Dificuldade de divulgação para pequenos prestadores**

Mecânicos e oficinas, especialmente estabelecimentos menores, podem ter dificuldade para divulgar seus serviços e alcançar novos clientes sem precisar criar e manter um site próprio ou investir em diferentes canais de divulgação.

O projeto pretende oferecer uma presença digital própria dentro da plataforma, permitindo que o prestador divulgue seus serviços, produtos, promoções e localização em um único ambiente.

**7. Dificuldade para construir e demonstrar reputação**

Clientes podem ter dificuldade para conhecer a experiência de outras pessoas com determinada oficina antes de contratar um serviço. Da mesma forma, mecânicos podem ter dificuldade para demonstrar a qualidade e a confiabilidade de seu trabalho para novos clientes.

O sistema de avaliações pretende criar um histórico público de experiências dos clientes, permitindo que os prestadores construam sua reputação dentro da plataforma.

**8. Falta de ferramentas para gerenciamento interno das oficinas**

Além da divulgação, pequenos prestadores podem não possuir uma ferramenta centralizada para organizar as informações relacionadas aos seus atendimentos.

A plataforma pretende oferecer recursos internos para o cadastro de veículos, clientes, serviços, peças, orçamentos, observações técnicas e histórico de manutenção, facilitando a organização dos atendimentos realizados pela oficina.

**9. Falta de histórico centralizado de manutenção**

Informações sobre manutenções anteriores podem ficar dispersas ou depender de registros físicos, dificultando a consulta do que já foi realizado em determinado veículo.

O projeto pretende possibilitar o registro do histórico de manutenção, incluindo serviços realizados, peças substituídas, observações e demais informações relevantes, permitindo que o prestador consulte essas informações em atendimentos futuros.

**10. Distanciamento entre divulgação e gestão do serviço**

As ferramentas utilizadas para divulgar uma oficina geralmente são separadas das ferramentas utilizadas para administrar seus atendimentos. Isso pode exigir que o prestador utilize diferentes sistemas ou meios para divulgar seu trabalho, conversar com clientes e controlar os serviços realizados.

O projeto pretende reunir essas funções em uma única plataforma, conectando a **divulgação do prestador**, a **comunicação com o cliente** e o **gerenciamento dos serviços automotivos**.

- [x] Definir o escopo do projeto

O projeto consiste no desenvolvimento de uma plataforma web voltada à localização, divulgação e gerenciamento de serviços automotivos, conectando proprietários de veículos a oficinas, mecânicos e outros estabelecimentos relacionados ao setor automotivo.

A plataforma terá como objetivo facilitar a localização de estabelecimentos de acordo com a necessidade do usuário, apresentar informações sobre os serviços oferecidos e proporcionar um meio de comunicação entre clientes e prestadores de serviços.

**Funcionalidades destinadas aos clientes**

O sistema deverá permitir que os usuários:

- Pesquisem oficinas e serviços automotivos;
- Visualizem oficinas e outros estabelecimentos relacionados ao setor automotivo em um mapa;
- Consultem os serviços, especialidades e áreas de atuação de cada oficina cadastrada;
- Visualizem informações sobre produtos, peças e acessórios disponibilizados pelas oficinas;
- Visualizem promoções e ofertas divulgadas pelos estabelecimentos;
- Entrem em contato com as oficinas por meio de um sistema de chat;
- Consultem avaliações realizadas por outros clientes;
- Realizem avaliações sobre serviços e atendimentos recebidos.

O mapa também poderá apresentar estabelecimentos que oferecem serviços específicos, como borracharias e postos de combustível que possuam calibragem de pneus. Esses estabelecimentos poderão aparecer como pontos de interesse no mapa sem necessariamente possuírem um cadastro completo como oficina na plataforma.

**Funcionalidades destinadas às oficinas e prestadores**

Prestadores de serviços que realizarem o cadastro oficial na plataforma terão acesso a uma área administrativa própria, permitindo:

- Criar e administrar o perfil da oficina;
- Informar serviços, especialidades e tipos de veículos atendidos;
- Gerenciar produtos, peças e acessórios disponíveis;
- Criar e administrar promoções;
- Cadastrar clientes e seus veículos;
- Manter informações detalhadas dos veículos, como marca, modelo, ano, versão, placa e quilometragem;
- Registrar problemas, peças e componentes que necessitam de manutenção;
- Criar e gerenciar orçamentos;
- Registrar serviços realizados e peças substituídas;
- Adicionar observações técnicas sobre os atendimentos;
- Acompanhar o andamento dos serviços;
- Manter o histórico de manutenção dos veículos;
- Comunicar-se com os clientes por meio do chat;
- Acompanhar as avaliações recebidas.

**Limitações do projeto**

A plataforma terá como função principal conectar clientes e prestadores, disponibilizar informações e auxiliar no gerenciamento dos serviços. A venda de produtos e serviços não será realizada diretamente pelo sistema.

Os catálogos das oficinas terão como finalidade apenas apresentar os produtos, peças e acessórios disponíveis no estabelecimento. Caso o cliente tenha interesse em realizar uma compra, a negociação será feita diretamente com a oficina, utilizando o chat ou outro meio de contato disponibilizado pelo estabelecimento.

Da mesma forma, a plataforma não será responsável inicialmente por pagamentos, entrega de produtos ou execução dos serviços automotivos.

**Fora do escopo**

Não fazem parte do escopo inicial do projeto:

- Sistema de pagamento integrado;
- Marketplace ou comércio eletrônico;
- Entrega de produtos;
- Execução ou contratação direta de serviços pela plataforma;
- Controle financeiro completo das oficinas;
- Controle contábil ou fiscal das empresas;
- Gestão de estoque avançada;
- Integração obrigatória com sistemas externos de oficinas;
- Desenvolvimento de um site individual para cada oficina.

O projeto poderá receber novas funcionalidades futuramente, mas elas não fazem parte da versão inicial definida neste escopo.

- [x] Definir as principais funções do sistema

- Buscar oficinas e serviços;
- Exibir estabelecimentos no mapa;
- Cadastrar oficinas;
- Gerenciar veículos;
- Gerenciar serviços de manutenção;
- Criar orçamentos;
- Manter histórico de manutenção;
- Comunicação por chat;
- Avaliações;
- Divulgação de promoções;
- Catálogo de produtos.

---

## Requisitos

- [x] Levantar requisitos funcionais

**Funções do Cliente**

1. Cliente deverá poder **se registrar e fazer login**.
2. Cliente deverá poder **editar seus dados pessoais e de acesso**.
3. Cliente deverá poder **cadastrar seus veículos**, incluindo suas informações, para facilitar o envio dos dados à oficina.
4. Cliente deverá poder **editar e remover veículos cadastrados**.
5. Cliente deverá poder **filtrar oficinas de acordo com suas necessidades**.
6. Cliente deverá poder **visualizar no mapa as oficinas que atendem aos filtros selecionados**.
7. Cliente deverá poder **visualizar os dados da oficina**, como endereço, contato, serviços oferecidos, produtos e avaliações.
8. Cliente deverá poder **favoritar oficinas** para encontrá-las posteriormente.
9. Cliente deverá poder **solicitar atendimento ou orçamento à oficina**.
10. Cliente deverá poder **se comunicar diretamente com o mecânico/oficina**.
11. Cliente deverá poder **receber e visualizar orçamentos**.
12. Cliente deverá poder **aceitar ou recusar um orçamento**.
13. Cliente deverá poder **consultar o status de um serviço em andamento**.
14. Cliente deverá poder **consultar o histórico de manutenções de seus veículos**.
15. Cliente deverá poder **verificar os produtos disponíveis para compra local**.
16. Cliente deverá poder **avaliar e comentar sobre a oficina**.
17. Cliente deverá poder **denunciar avaliações, anúncios ou conteúdos inadequados**.

**Funções do Mecânico/Oficina (M/O)**

1. M/O deverá poder **se registrar e fazer login**.
2. M/O deverá poder **editar os dados da oficina e os serviços oferecidos**.
3. M/O deverá poder **cadastrar os serviços oferecidos pela oficina**.
4. M/O deverá poder **receber e gerenciar solicitações de atendimento e orçamento**.
5. M/O deverá poder **visualizar os dados do veículo fornecidos pelo cliente**.
6. M/O deverá poder **cadastrar e atualizar informações técnicas do veículo durante o atendimento**.
7. M/O deverá poder **elaborar e enviar orçamentos ao cliente**.
8. M/O deverá poder **se comunicar diretamente com o cliente**.
9. M/O deverá poder **atualizar o status do serviço em andamento**.
10. M/O deverá poder **registrar os serviços realizados no veículo**.
11. M/O deverá poder **consultar o histórico de manutenções dos veículos atendidos**.
12. M/O deverá poder **cadastrar e gerenciar os produtos disponíveis para venda**.
13. M/O deverá poder **definir os preços e a disponibilidade dos produtos**.
14. M/O deverá poder **disponibilizar um catálogo dos produtos vendidos pela loja**, sem permitir a compra diretamente pela plataforma.
15. M/O deverá poder **criar e gerenciar promoções e anúncios**.
16. M/O deverá poder **contratar divulgações pagas de promoções pela plataforma** (especificar parte da plataforma no RN).
17. M/O deverá poder **visualizar e responder às avaliações dos clientes**.

**Funções do Sistema**

1. Sistema deverá poder **exibir oficinas de acordo com a localização e os filtros selecionados pelo cliente**.
2. Sistema deverá poder **calcular e exibir a distância entre o cliente e as oficinas**.
3. Sistema deverá poder **enviar notificações sobre mensagens, orçamentos e alterações no atendimento**.
4. Sistema deverá poder **gerenciar os pagamentos referentes às divulgações de promoções**.
5. Sistema deverá poder **controlar a disponibilidade dos produtos cadastrados pelas oficinas**.
6. Sistema deverá poder **moderar avaliações, comentários e anúncios**.
7. Sistema deverá poder **gerenciar as contas de clientes e M/O**.

- [x] Levantar requisitos não funcionais

**RNF01 – Tecnologias do Frontend:** O frontend do sistema deverá ser desenvolvido utilizando **HTML5** para a estrutura das páginas, **CSS3** para estilização e **JavaScript** para implementação da lógica e interatividade da interface.

**RNF02 – Tecnologias do Backend:** O backend deverá ser desenvolvido utilizando **Python** e o framework **Django**, sendo responsável pelo processamento das regras de negócio, gerenciamento das requisições e comunicação com o banco de dados.

**RNF03 – Sistema Gerenciador de Banco de Dados:** O sistema deverá utilizar o **PostgreSQL** como Sistema Gerenciador de Banco de Dados (SGBD), utilizando um banco de dados relacional para armazenamento e organização das informações do sistema.

**RNF04 – Arquitetura do Sistema:** O sistema deverá utilizar uma arquitetura **cliente-servidor**, com separação entre frontend, backend e banco de dados. O backend será responsável pelas regras de negócio e acesso aos dados, enquanto o frontend será responsável pela apresentação e interação com o usuário.

**RNF05 – API:** O sistema deverá disponibilizar uma **API REST** desenvolvida utilizando **Django REST Framework (DRF)**, utilizando **JSON** para comunicação entre frontend e backend. A API deverá seguir o padrão **OpenAPI** e disponibilizar documentação adequada de seus endpoints.

**RNF06 – Segurança:** O sistema deverá utilizar **HTTPS** em ambiente de produção e realizar validação e sanitização dos dados recebidos. O backend deverá utilizar os mecanismos de segurança disponibilizados pelo Django e adotar medidas de proteção contra vulnerabilidades comuns, incluindo SQL Injection, XSS, CSRF e acesso não autorizado.

**RNF07 – Autenticação:** O sistema deverá utilizar mecanismos de autenticação fornecidos pelo **Django**, permitindo identificar os usuários autenticados e controlar o acesso às funcionalidades restritas. As senhas deverão ser armazenadas utilizando **hash seguro**, nunca em texto puro.

**RNF08 – Desempenho:** O sistema deverá apresentar tempo de resposta adequado para as operações realizadas pelos usuários, evitando processamento desnecessário e consultas ineficientes ao banco de dados.

**RNF09 – Responsividade:** A interface deverá possuir design responsivo, adaptando-se adequadamente a **computadores, tablets e smartphones**, sem perda das principais funcionalidades.

**RNF10 – Compatibilidade:** O sistema deverá funcionar nas versões atuais dos principais navegadores, incluindo **Google Chrome, Mozilla Firefox, Microsoft Edge e Safari**, mantendo o funcionamento das principais funcionalidades.

**RNF11 – Disponibilidade:** O sistema deverá permanecer disponível durante os períodos de operação definidos para o projeto, buscando minimizar interrupções decorrentes de falhas no servidor ou nos serviços utilizados.

**RNF12 – Escalabilidade:** A estrutura do sistema deverá permitir o aumento da quantidade de usuários, oficinas, serviços e demais registros sem exigir uma alteração completa da arquitetura do sistema.

**RNF13 – Manutenibilidade:** O código deverá ser organizado e dividido em módulos, seguindo as boas práticas recomendadas pelo Django. O frontend, backend e componentes de acesso aos dados deverão possuir estrutura organizada, facilitando a manutenção, correção de erros e implementação de novas funcionalidades.

**RNF14 – Acessibilidade:** A interface deverá seguir boas práticas de acessibilidade, utilizando elementos HTML semânticos, textos alternativos para imagens, contraste adequado e navegação por teclado sempre que aplicável.

**RNF15 – Backup e Recuperação:** O banco de dados deverá possuir mecanismos de backup periódico, permitindo a recuperação dos dados em caso de falha, corrupção ou perda das informações.

**RNF16 – Monitoramento e Logs:** O backend deverá registrar erros e eventos relevantes da aplicação por meio do sistema de **logging do Django**, permitindo identificar problemas durante a execução e auxiliar na manutenção do sistema.

**RNF17 – Testes:** O sistema deverá possuir testes para validar suas principais funcionalidades, incluindo testes do backend, API e integração com o banco de dados, além de testes das principais funcionalidades da interface.

**RNF18 – Hospedagem e Infraestrutura:** O sistema deverá ser executado em uma infraestrutura compatível com **Python, Django e PostgreSQL**, utilizando **HTTPS** em ambiente de produção. A utilização de **Docker** poderá ser adotada para facilitar a configuração e implantação dos componentes do sistema.

## Stack

- **Frontend:** HTML5 + CSS3 + JavaScript
- **Backend:** Python + Django
- **API:** Django REST Framework (REST + JSON)
- **Banco:** PostgreSQL
- **ORM:** Django ORM
- **Validação:** Django Forms / Django REST Framework Serializers
- **Documentação da API:** OpenAPI/Swagger
- **Autenticação:** Django Authentication
- **Servidor:** Gunicorn
- **Infraestrutura:** Docker


- [x] Definir as regras de negócio básicas
### 1. Regras de Negócio Básicas
As regras abaixo estabelecem os limites e comportamentos obrigatórios do sistema, servindo de base tanto para o desenho das telas quanto para a futura implementação.

#### 1.1 Usuários e cadastro
*   **RN01:** Todo usuário deve se cadastrar como Cliente ou como Oficina (prestador de serviço); os dois perfis não se confundem, mas a mesma pessoa pode ter os dois tipos de conta.
*   **RN02:** Uma Oficina só obtém acesso à área administrativa completa após concluir um cadastro oficial (dados do estabelecimento, endereço e serviços oferecidos).
*   **RN03:** Uma Oficina só pode visualizar e gerenciar veículos, clientes, orçamentos e serviços vinculados ao seu próprio estabelecimento.

#### 1.2 Veículos e manutenção
*   **RN04:** Todo registro de manutenção deve estar vinculado a um veículo previamente cadastrado (marca, modelo, ano, versão, placa e quilometragem).
*   **RN05:** O histórico de manutenção de um veículo é acumulativo e não pode ser apagado, apenas complementado com novos registros.
*   **RN06:** Cada item de manutenção (óleo, pneus, revisão, pastilhas, bateria, entre outros) deve poder ser registrado individualmente, com data e quilometragem, para permitir o cálculo da próxima manutenção prevista.

#### 1.3 Orçamentos e status do serviço
*   **RN07:** Um orçamento só pode ser enviado ao cliente se contiver peças e/ou mão de obra, com valores e o custo total estimado.
*   **RN08:** O status de um atendimento segue uma sequência fixa: orçamento → aguardando aprovação → em manutenção → (aguardando peça, se necessário) → serviço concluído → veículo entregue; a Oficina não pode pular etapas essenciais.
*   **RN09:** Somente a Oficina responsável pode alterar o status de um atendimento em andamento.

#### 1.4 Catálogo, promoções e comércio
*   **RN10:** O catálogo de peças e produtos é apenas informativo: mostra o que a Oficina tem disponível, mas não processa vendas nem pagamentos dentro da plataforma.
*   **RN11:** Toda negociação de compra, preço final ou entrega de peças ocorre fora do sistema, por meio do chat ou dos contatos divulgados pela Oficina.
*   **RN12:** Promoções cadastradas por uma Oficina devem ter uma data de validade; ao expirar, deixam de ser exibidas automaticamente na tela inicial.

#### 1.5 Comunicação e avaliação
*   **RN13:** Toda comunicação entre Cliente e Oficina deve ocorrer pelo chat interno da plataforma, mantendo um histórico consultável por ambas as partes.
*   **RN14:** Um Cliente só pode avaliar um atendimento depois que o status estiver marcado como concluído/entregue, e apenas uma avaliação por atendimento é permitida.

- [x] Definir os principais fluxos de utilização
### 2. Principais Fluxos de Utilização
Dois perfis concentram praticamente todo o uso do sistema: o Cliente (dono do veículo) e a Oficina (prestador de serviço). Os fluxos abaixo descrevem o caminho típico de cada um, do início ao fim de um atendimento.

### 2.1 Fluxo do Cliente — encontrar e contratar um serviço
1.  **Cadastro/login** — o usuário cria conta ou entra na plataforma.
2.  **Busca de oficina** — pesquisa por serviço (ex.: troca de óleo, funilaria), localização ou tipo de veículo.
3.  **Consulta ao perfil da oficina** — visualiza serviços oferecidos, especialidades, catálogo de peças, promoções ativas e avaliações de outros clientes.
4.  **Contato via chat** — inicia conversa para tirar dúvidas, descrever o problema ou negociar um produto do catálogo.
5.  **Recebimento do orçamento** — a oficina envia peças, mão de obra e valor total; o cliente aprova ou recusa pelo chat.
6.  **Acompanhamento do status** — o cliente acompanha as etapas do atendimento (em manutenção, aguardando peça, concluído etc.).
7.  **Retirada e avaliação** — após a entrega do veículo, o cliente avalia o serviço prestado.

#### 2.2 Fluxo da Oficina — divulgar e gerenciar atendimentos
1.  **Cadastro oficial** — a oficina registra dados do estabelecimento, serviços e especialidades.
2.  **Configuração do perfil** — cadastra catálogo de peças/produtos e promoções que aparecerão para os clientes.
3.  **Atendimento pelo chat** — recebe contato de um cliente interessado em um serviço ou produto.
4.  **Cadastro do veículo e do cliente** — caso ainda não existam na base da oficina, registra os dados completos do veículo e do proprietário.
5.  **Elaboração do orçamento** — informa peças, mão de obra e valores, enviando para aprovação do cliente.
6.  **Execução do serviço** — atualiza o status conforme o andamento (em manutenção, aguardando peça etc.) e registra peças substituídas.
7.  **Registro técnico** — adiciona observações sobre o que foi encontrado ou realizado no veículo.
8.  **Conclusão** — marca o serviço como concluído e o veículo como entregue.
9.  **Consulta futura** — usa o histórico de manutenção do veículo em atendimentos posteriores, evitando retrabalho de diagnóstico.

#### 2.3 Fluxo de manutenção preventiva
Este fluxo é o que conecta o cadastro de veículo feito pela oficina ao aviso de manutenção futura:
1.  A oficina registra um item de manutenção realizado (ex.: troca de óleo) com data e quilometragem.
2.  O sistema calcula a próxima data/quilometragem prevista para esse mesmo item.
3.  Quando a manutenção se aproxima, o cliente (e opcionalmente a oficina que realizou o último serviço) recebe um aviso.
4.  O cliente pode usar esse aviso como gatilho para buscar uma oficina novamente pela plataforma.

- [x] Priorizar as funcionalidades que realmente serão implementadas
### 3. Priorização das Funcionalidades (Método MoSCoW)

Para viabilizar a entrega em grupo, as funcionalidades foram organizadas pelo método MoSCoW, separando o que é essencial para uma primeira versão funcional (MVP) do que pode ficar para etapas seguintes.

#### 3.1 Must have (Deve ter)
*   **Cadastro de clientes e de oficinas:** Registro inicial de ambos os perfis na plataforma.
*   **Cadastro completo de veículos:** Inclusão de marca, modelo, ano, placa e quilometragem.
*   **Registro de manutenção e histórico:** Armazenamento cumulativo dos serviços do veículo.
*   **Criação de orçamentos:** Detalhamento de peças, mão de obra e cálculo do valor total.
*   **Chat direto:** Canal de comunicação em tempo real entre cliente e oficina.
*   **Acompanhamento de status:** Visualização das etapas do atendimento em andamento.

#### 3.2 Should have (Deveria ter)
*   **Catálogo de peças e produtos:** Exibição do estoque disponível, funcionando de forma apenas informativa.
*   **Promoções na tela inicial:** Vitrine de ofertas ativas configuradas pela oficina.
*   **Avaliações de clientes:** Sistema de notas e comentários sobre o atendimento concluído.
*   **Observações técnicas:** Espaço para o mecânico registrar detalhes técnicos do serviço.

#### 3.3 Could have (Poderia ter)
*   **Aviso automático de manutenção:** Alertas preventivos baseados no cálculo de tempo e quilometragem.
*   **Mapa de localização:** Busca visual de oficinas próximas e pontos de interesse.
*   **Anúncios de veículos:** Espaço para divulgação de venda de automóveis, indo além dos serviços.

#### 3.4 Won't have (Não terá agora)
*   **Pagamento integrado:** Transações financeiras diretas pela plataforma.
*   **Marketplace de peças:** E-commerce nativo para compra e venda de componentes automotivos.
*   **Serviço de entrega:** Logística para envio e distribuição de produtos.
*   **Controle financeiro da oficina:** Módulo contábil ou de fluxo de caixa completo para o estabelecimento.
*   **Integrações obrigatórias:** Conexão forçada com sistemas de gestão externos.

## 3. Modelagem do sistema

- [x] Identificar os atores/usuários
1. **Cliente** — proprietário do veículo. Pode cadastrar veículos, buscar oficinas, conversar pelo chat, receber e aprovar/recusar orçamentos, acompanhar serviços e avaliar atendimentos.
2. **Oficina** — prestador de serviços automotivos. Pode cadastrar seus dados e serviços, gerenciar clientes e veículos vinculados, criar orçamentos, atualizar status, registrar manutenções, manter catálogo e promoções.
- [x] Identificar as principais entidades e objetos

- **Usuário** — dados básicos de acesso à plataforma.
- **Cliente** — usuário que possui/gerencia veículos.
- **Oficina** — estabelecimento que presta serviços.
- **Veículo** — veículo do cliente.
- **Atendimento** — representa um serviço que está sendo realizado para um veículo.
- **Orçamento** — proposta de preço feita pela oficina para um atendimento.
- **Item do Orçamento** — peças e/ou mão de obra que compõem o orçamento.
- **Peça/Produto** — itens que a oficina disponibiliza no catálogo.
- **Serviço** — serviços oferecidos pela oficina, como troca de óleo, revisão, funilaria etc.
- **Manutenção** — registro de uma manutenção realizada no veículo.
- **Promoção** — oferta cadastrada pela oficina, com validade.
- **Conversa/Chat** — conversa entre cliente e oficina.
- **Mensagem** — mensagens enviadas dentro de uma conversa.
- **Avaliação** — nota e comentário do cliente sobre um atendimento.

- [x] Fazer diagrama de casos de uso


## 4. Design / Interface

- [x] **Definir identidade visual**
  - Nome: SAM (Simple Auto Maintenance), com o slogan "Your car • Your care".
  - Tom: automotivo com ar editorial/retrô, fundo creme, blocos vermelhos e imagem de carros esportivos (hero com dois carros brancos em um túnel, gerada por IA).
  - Cantos bem arredondados (pílulas) e bastante espaço em branco.
  - Idioma misto: navegação em inglês (HOME, MAP, CHAT, VEHICLE) e conteúdo em português.

- [x] **Criar/definir logo**
  - Wordmark "SAM" em preto, em fonte itálica pesada, com silhueta de carro acima e "SIMPLE AUTO MAINTENANCE" abaixo.
  - Detalhes em vermelho (traços laterais e um ícone no meio das letras).
  - Fica no canto superior esquerdo do header.

- [x] **Definir paleta de cores** (valores estimados visualmente, vale confirmar no código)
  - Fundo principal: creme/bege, ~`#EDE8DC`
  - Vermelho escuro (item ativo do menu, blocos do título): ~`#B22222`
  - Vermelho-alaranjado (botões primários, bloco "SAM", balões enviados, avatares): ~`#FF3B2F`
  - Verde-oliva/sálvia claro (mapa, cabeçalho do chat, fundo com padrão): ~`#C9CCB0` a `#DAD8C6`
  - Branco: cards, campo de busca e balões recebidos
  - Preto/cinza escuro: textos e bordas
  - Apoio: laranja/âmbar para o avatar de outra oficina, verde para o indicador "online"

- [x] **Definir tipografia**
  - Títulos de destaque (hero): serifada de display, em caixa alta com espaçamento entre letras, no estilo Playfair Display. Branca sobre bloco vermelho.
  - Interface e corpo do texto: sans-serif geométrica no estilo Poppins.
  - Menu: caixa alta, pequena, com letter-spacing.
  - Subtítulo do hero: itálico em vermelho.
  - Títulos de página e de seção (ex.: "Cadastrar veículo"): Poppins semibold.
  - Labels de formulário: Poppins pequena, com asterisco vermelho nos campos obrigatórios.

- [x] **Definir estilo dos componentes da interface**
  - **Header:** logo à esquerda, menu centralizado e ação à direita ("Entrar", ou "Usuário" + "Sair" quando logado).
  - **Menu:** item ativo em pílula vermelho-escura com texto branco.
  - **Botões:** primário em pílula preenchida vermelho-alaranjada ("Encontrar oficina", "Cadastrar minha oficina"). Secundário em pílula só com contorno ("Sou oficina", "Entrar", "Sair").
  - **Chips de filtro:** pílulas com contorno fino (Mecânica, Elétrica, Pneus, Funilaria e pintura).
  - **Busca:** campo branco arredondado com ícone de lupa.
  - **Cards:** brancos, com cantos bem arredondados (~20px) e sem sombra forte. Incluem estado vazio com título, texto e CTA.
  - **Inputs e selects:** fundo bege, borda suave, cantos arredondados. Textarea redimensionável e upload de arquivos (até 3 fotos) ainda com o estilo nativo do navegador.
  - **Chat:** balões enviados em vermelho-alaranjado, recebidos em branco com borda preta, horário dentro do balão e fundo com padrão de rabiscos em verde-sálvia. Barra de entrada branca com ícones de anexo, veículo e enviar.
  - **Lista de conversas:** painel lateral verde-claro com busca, avatar circular, nome, prévia da mensagem e horário.
  - **Stepper de status do serviço:** Orçamento → Aguardando aprovação → Em manutenção → Concluído → Entregue, com linha e pontos, e etapa atual destacada em vermelho.

- [x] **Definir estrutura das principais páginas**
  - **Home:** hero dividido em duas colunas. À esquerda: título em blocos vermelhos, slogan, texto de apoio e dois CTAs. À direita: foto grande.
  - **Map:** barra de busca, chips de categoria, mapa à esquerda e lista "Oficinas próximas" à direita (hoje com estado vazio e CTA para cadastrar oficina).
  - **Vehicle (Cadastrar veículo):** formulário em 3 cards de seção, com grade de 3 colunas.
    - *Informações essenciais:* marca, modelo, ano de fabricação, ano-modelo, quilometragem e placa.
    - *Mecânica e aparência:* combustível, câmbio, versão, motorização e cor.
    - *Informações complementares:* observações e fotos (até 3).
  - **Chat:** duas colunas, com lista de conversas à esquerda e conversa ativa à direita (cabeçalho da oficina com status online, stepper do serviço, mensagens e campo de envio).

**Pontos para revisar:**
- O campo de upload de fotos ainda usa o estilo padrão do navegador, fora da identidade visual.

## 5. Banco de dados

- [x] Identificar as informações que precisam ser armazenadas
- [x] Identificar as entidades/tabelas
- [x] Definir os atributos
- [x] Definir chaves primárias
- [x] Definir chaves estrangeiras
- [x] Definir os relacionamentos
- [x] Criar o modelo conceitual
- [x] Criar o modelo lógico
- [x] Definir a estrutura física do banco
- [x] Criar o banco de dados

## 6. Desenvolvimento

- [x] Preparar estrutura inicial do projeto
- [x] Desenvolver a estrutura HTML
- [x] Desenvolver o CSS/interface
- [x] Implementar funcionalidades com JavaScript
- [x] Implementar o backend, se necessário
- [x] Integrar o sistema ao banco de dados — PostgreSQL com `database/init.sql` + migrations; API Django/DRF (backend, Fases 1–4)
- [x] Implementar as funcionalidades definidas nos requisitos — 84 endpoints da especificação + 6 de apoio, integrados às 26 telas (Fases 3–5); *Won't have* fora do escopo

## 7. Testes

- [x] Testar cada funcionalidade individualmente — ~1.950 testes automatizados no PostgreSQL real (backend)
- [x] Testar integração entre frontend, backend e banco — contrato (90 operações) e E2E F1–F8 + mesma origem com CSP no Chromium
- [x] Testar formulários e validações — limites de campo = `maxlength` das telas, erros 400 por campo, uploads (Fase 6)
- [ ] Testar diferentes tamanhos de tela — *pendente: os E2E rodam só em desktop (1280×900) e só no Chromium; Firefox, WebKit e celular a fazer*
- [x] Corrigir erros encontrados — defeitos achados pelos testes corrigidos e registrados no `README.md` (seção 7)
- [ ] Fazer teste final do sistema — *pendente: validação em staging e aceite (BE-094, `backend/docs/ACEITE.md`)*

## 8. Documentação e entrega

- [x] Organizar os diagramas finais — `docs/DIAGRAMA_SAM.svg` gerado do banco (confere com o `init.sql`); original em `docs/historico/`
- [x] Documentar os requisitos — este arquivo e `backlog/backlog_backend.md`
- [x] Documentar a estrutura do banco — `database/init.sql` comentado, diagrama, `backend/docs/migrations.md`
- [x] Documentar as principais funcionalidades — `README.md`, OpenAPI (`/api/docs/`), ADRs, `backend/docs/RUNBOOK.md`
- [ ] Revisar o projeto — *pendente: revisão por outra pessoa seguindo o runbook (BE-093/BE-094)*
- [ ] Preparar apresentação/demonstração
- [ ] Fazer entrega final

## Estrutura resumida

Se quiser deixar o backlog bem enxuto, eu organizaria em apenas oito grandes blocos:

> Projeto → Requisitos → Modelagem → Design → Banco de Dados → Desenvolvimento → Testes → Documentação

E dentro de cada bloco você vai detalhando apenas o necessário. Isso evita cair naquele problema de tentar especificar cada mínimo detalhe antes mesmo de saber como o projeto vai funcionar.
