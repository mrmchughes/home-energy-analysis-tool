import { useForm, getFormProps } from '@conform-to/react'
import { parseWithZod } from '@conform-to/zod'
import { invariantResponse } from '@epic-web/invariant'
import { cssBundleHref } from '@remix-run/css-bundle'
import {
	json,
	type LoaderFunctionArgs,
	type ActionFunctionArgs,
	type HeadersFunction,
	type LinksFunction,
	type MetaFunction,
} from '@remix-run/node'

import {
	Form,
	Link,
	Links,
	LiveReload,
	Meta,
	Outlet,
	Scripts,
	ScrollRestoration,
	useFetcher,
	useFetchers,
	useLoaderData,
	useMatches,
	useSubmit,
} from '@remix-run/react'
import { withSentry } from '@sentry/remix'
import { useRef } from 'react'
import { HoneypotProvider } from 'remix-utils/honeypot/react'
import { z } from 'zod'
import { GeneralErrorBoundary } from './components/error-boundary.tsx'
import { EpicProgress } from './components/progress-bar.tsx'
import { SearchBar } from './components/search-bar.tsx'
import { useToast } from './components/toaster.tsx'
import { Button } from './components/ui/button.tsx'
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuPortal,
	DropdownMenuTrigger,
} from './components/ui/dropdown-menu.tsx'
import { Icon, href as iconsHref } from './components/ui/icon.tsx'
import { EpicToaster } from './components/ui/sonner.tsx'
import tailwindStyleSheetUrl from './styles/tailwind.css'
import './App.css'

import { getUserId, logout } from './utils/auth.server.ts'
import { ClientHintCheck, getHints, useHints } from './utils/client-hints.tsx'
import { prisma } from './utils/db.server.ts'
import { getEnv } from './utils/env.server.ts'
import {
	combineServerTimings,
	makeTimings,
	time,
} from './utils/timing.server.ts'
import { WeatherExample } from './components/WeatherExample.tsx'
import { Weather } from './WeatherExample.js'
import { honeypot } from './utils/honeypot.server.ts'
import { combineHeaders, getDomainUrl, getUserImgSrc } from './utils/misc.tsx'
import { useNonce } from './utils/nonce-provider.ts'
import { useRequestInfo } from './utils/request-info.ts'
import { type Theme, setTheme, getTheme } from './utils/theme.server.ts'
import { getToast } from './utils/toast.server.ts'
import { useOptionalUser, useUser } from './utils/user.ts'

export const links: LinksFunction = () => {
	return [
		// Preload svg sprite as a resource to avoid render blocking
		{ rel: 'preload', href: iconsHref, as: 'image' },
		// Preload CSS as a resource to avoid render blocking
		{ rel: 'preload', href: tailwindStyleSheetUrl, as: 'style' },
		cssBundleHref ? { rel: 'preload', href: cssBundleHref, as: 'style' } : null,
		{ rel: 'mask-icon', href: '/favicons/mask-icon.svg' },
		{
			rel: 'alternate icon',
			type: 'image/png',
			href: '/favicons/favicon-32x32.png',
		},
		{ rel: 'apple-touch-icon', href: '/favicons/apple-touch-icon.png' },
		{
			rel: 'manifest',
			href: '/site.webmanifest',
			crossOrigin: 'use-credentials',
		} as const, // necessary to make typescript happy
		//These should match the css preloads above to avoid css as render blocking resource
		{ rel: 'icon', type: 'image/svg+xml', href: '/favicons/favicon.svg' },
		{ rel: 'stylesheet', href: tailwindStyleSheetUrl },
		cssBundleHref ? { rel: 'stylesheet', href: cssBundleHref } : null,
	].filter(Boolean)
}

export const meta: MetaFunction<typeof loader> = ({ data }) => {
	return [
		{ title: data ? 'Epic Notes' : 'Error | Epic Notes' },
		{ name: 'description', content: `Your own captain's log` },
	]
}

export async function loader({ request }: LoaderFunctionArgs) {
	const timings = makeTimings('root loader')
	const userId = await time(() => getUserId(request), {
		timings,
		type: 'getUserId',
		desc: 'getUserId in root',
	})

	const user = userId
		? await time(
				() =>
					prisma.user.findUniqueOrThrow({
						select: {
							id: true,
							name: true,
							username: true,
							image: { select: { id: true } },
							roles: {
								select: {
									name: true,
									permissions: {
										select: { entity: true, action: true, access: true },
									},
								},
							},
						},
						where: { id: userId },
					}),
				{ timings, type: 'find user', desc: 'find user in root' },
			)
		: null
	// if (userId && !user) {
	// 	console.info('something weird happened')
	// 	// something weird happened... The user is authenticated but we can't find
	// 	// them in the database. Maybe they were deleted? Let's log them out.
	// 	await logout({ request, redirectTo: '/' })
	// }
	// const { toast, headers: toastHeaders } = await getToast(request)
	const honeyProps = honeypot.getInputProps()
	// Weather station data
	const w_href: string =
		'https://archive-api.open-meteo.com/v1/archive?latitude=52.52&longitude=13.41&daily=temperature_2m_max&timezone=America%2FNew_York&start_date=2022-01-01&end_date=2023-08-30&temperature_unit=fahrenheit'
	const w_res: Response = await fetch(w_href)
	const weather: Weather = (await w_res.json()) as Weather

	return json(
		{
			weather,
			user,
			requestInfo: {
				hints: getHints(request),
				origin: getDomainUrl(request),
				path: new URL(request.url).pathname,
				userPrefs: {
					theme: getTheme(request),
				},
			},
			ENV: getEnv(),
			honeyProps,
		},
		{
			headers: combineHeaders({ 'Server-Timing': timings.toString() }),
		},
	)
}

/**
 * Step 4 of making Server Timings
 * https://github.com/epicweb-dev/epic-stack/blob/main/docs/server-timing.md
 */
export const headers: HeadersFunction = ({ loaderHeaders }) => {
	const headers = {
		'Server-Timing': loaderHeaders.get('Server-Timing') ?? '',
	}
	return headers
}

function Document({
	children,
	nonce,
	env = {},
}: {
	children: React.ReactNode
	nonce: string
	env?: Record<string, string>
}) {
	return (
		<html lang="en" className={`h-full overflow-x-hidden`}>
			<head>
				<Meta />
				<meta charSet="utf-8" />
				<meta name="viewport" content="width=device-width,initial-scale=1" />
				<Links />
			</head>
			<body className="bg-background text-foreground">
				<div className="container items-center justify-between gap-4 md:h-24 md:flex-row">
					{children}
				</div>
				<script
					nonce={nonce}
					dangerouslySetInnerHTML={{
						__html: `window.ENV = ${JSON.stringify(env)}`,
					}}
				/>
				<ScrollRestoration nonce={nonce} />
				<Scripts nonce={nonce} />
				<LiveReload nonce={nonce} />
			</body>
		</html>
	)
}

function App() {
	const data = useLoaderData<typeof loader>()
	const nonce = useNonce()
	const user = useOptionalUser()
	const matches = useMatches()
	const isOnSearchPage = matches.find(m => m.id === 'routes/users+/index')
	const searchBar = isOnSearchPage ? null : <SearchBar status="idle" />

	return (
		<Document nonce={nonce} env={data.ENV}>
			<div className="flex h-screen flex-col justify-between">
				<header className="container py-6">
					{
						<nav className="flex flex-wrap items-center justify-between gap-4 sm:flex-nowrap md:gap-8">
							<TopLinks />
							<div className="flex items-center gap-10">
								{user ? (
									<UserDropdown />
								) : (
									<Button asChild variant="default" size="lg">
										{/* <Link to="/login">Log In</Link> */}
									</Button>
								)}
							</div>
							<div className="block w-full sm:hidden">{searchBar}</div>
						</nav>
					}
				</header>

				<div className="flex-1">
					<div>Site header</div>
					<hr />
					<br />
					<Outlet />
					<br />
					<hr />
					<div>Site footer</div>
				</div>

				<div className="container flex justify-between pb-5">
					<TopLinks />
				</div>
			</div>
			<EpicProgress />
		</Document>
	)
}

function TopLinks() {
	return (
		<>
			<Link to="/single" className="group grid leading-snug">
				<span className="font-light transition group-hover:-translate-x-1">
					single form
				</span>
			</Link>
			<Link to="/" className="group grid leading-snug">
				<span className="font-light transition group-hover:-translate-x-1">
					developers
				</span>
			</Link>
		</>
	)
}

function AppWithProviders() {
	const data = useLoaderData<typeof loader>()
	return (
		<HoneypotProvider {...data.honeyProps}>
			<App />
		</HoneypotProvider>
	)
}

export default withSentry(AppWithProviders)

function UserDropdown() {
	const user = useUser()
	const submit = useSubmit()
	const formRef = useRef<HTMLFormElement>(null)
	return (
		<DropdownMenu>
			<DropdownMenuTrigger asChild>
				<Button asChild variant="secondary">
					<Link
						to={`/users/${user.username}`}
						// this is for progressive enhancement
						onClick={e => e.preventDefault()}
						className="flex items-center gap-2"
					>
						<img
							className="h-8 w-8 rounded-full object-cover"
							alt={user.name ?? user.username}
							src={getUserImgSrc(user.image?.id)}
						/>
						<span className="text-body-sm font-bold">
							{user.name ?? user.username}
						</span>
					</Link>
				</Button>
			</DropdownMenuTrigger>
			<DropdownMenuPortal>
				<DropdownMenuContent sideOffset={8} align="start">
					<DropdownMenuItem asChild>
						<Link prefetch="intent" to={`/users/${user.username}`}>
							<Icon className="text-body-md" name="avatar">
								Profile
							</Icon>
						</Link>
					</DropdownMenuItem>
					<DropdownMenuItem asChild>
						<Link prefetch="intent" to={`/users/${user.username}/notes`}>
							<Icon className="text-body-md" name="pencil-2">
								Notes
							</Icon>
						</Link>
					</DropdownMenuItem>
					<DropdownMenuItem
						asChild
						// this prevents the menu from closing before the form submission is completed
						onSelect={event => {
							event.preventDefault()
							submit(formRef.current)
						}}
					>
						<Form action="/logout" method="POST" ref={formRef}>
							<Icon className="text-body-md" name="exit">
								<button type="submit">Logout</button>
							</Icon>
						</Form>
					</DropdownMenuItem>
				</DropdownMenuContent>
			</DropdownMenuPortal>
		</DropdownMenu>
	)
}

export function ErrorBoundary() {
	// the nonce doesn't rely on the loader so we can access that
	const nonce = useNonce()

	// NOTE: you cannot use useLoaderData in an ErrorBoundary because the loader
	// likely failed to run so we have to do the best we can.
	// We could probably do better than this (it's possible the loader did run).
	// This would require a change in Remix.

	// Just make sure your root route never errors out and you'll always be able
	// to give the user a better UX.

	return (
		<Document nonce={nonce}>
			<GeneralErrorBoundary />
		</Document>
	)
}
